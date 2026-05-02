#%%
import pandas as pd
#pd.options.mode.string_storage = "python"
import numpy as np
import pypsa
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from datapreparation import (
    demand_north, demand_south, demand_north_east, demand_south_east,
    wind_cf_hourly, solar_cf_hourly, cop_hourly, dhw_heat_hourly,
)
import importlib
import parameters
importlib.reload(parameters)
from parameters import (
    capital_cost, opex_cost, marginal_cost, lifetime,
    max_capacity_hydro,max_capacity_biomass, annuity, annualized_cost, DISCOUNT_RATE, methane_capacity,
    gas_efficiency,
)
#%% Adding the buses to the network
network = pypsa.Network()

network.add(
    "Carrier",
    ["hydro", "biomass", "nuclear", "wind", "solar", "battery", "gas", "heat", "heat_pump", "gas_boiler_local"],
    nice_name=["Hydro", "Biomass", "Nuclear", "Wind", "Solar", "Battery", "Gas", "Heat", "Heat pump", "Local gas boiler"],
    color=["aquamarine", "sienna", "purple", "dodgerblue", "gold", "violet", "gray", "red", "orange", "brown"]
)
network.add("Carrier", "AC")

# CO2 intensities (tCO2/MWh_primary)
network.carriers.loc["gas", "co2_emissions"] = 0.19
network.carriers.loc["biomass", "co2_emissions"] = 0.210
for c in ["hydro", "nuclear", "wind", "solar", "battery", "heat", "heat_pump", "gas_boiler_local", "AC"]:
    network.carriers.loc[c, "co2_emissions"] = 0.0


network.add("Bus", "bus BRA-N",
            v_nom=400.0,
            carrier="AC",
            x=-60.0, y=-3.0)

network.add("Bus", "bus BRA-NE",
            v_nom=400.0,
            carrier="AC",
            x=-38.5, y=-12.9)

network.add("Bus", "bus BRA-SE",
            v_nom=400.0,
            carrier="AC",
            x=-46.6, y=-19.5)

network.add("Bus", "bus BRA-S",
            v_nom=400.0,
            carrier="AC",
            x=-51.2, y=-30.0)


# Adding the network lines between the buses
network.add("Line"," line N-NE", bus0="bus BRA-N", bus1="bus BRA-NE", x=0.1, r=0.01, carrier="AC", s_nom=1100) 
network.add("Line"," line NE-SE", bus0="bus BRA-NE", bus1="bus BRA-SE", x=0.1, r=0.01, carrier="AC", s_nom=1100)
network.add("Line"," line SE-S", bus0="bus BRA-SE", bus1="bus BRA-S", x=0.1, r=0.01, carrier="AC", s_nom=1100)
network.add("Line"," line SE-N", bus0="bus BRA-SE", bus1="bus BRA-N", x=0.1, r=0.01, carrier="AC", s_nom=1100)

region_cf_map = {"BRA-N":"N","BRA-S":"S","BRA-NE":"NE","BRA-SE":"SE"}
regions = ["BRA-N","BRA-NE","BRA-SE","BRA-S"]
technologies = ["hydro","biomass","nuclear","wind","solar"]
region_bus_coords = {
    "BRA-N": (-60.0, -3.0),
    "BRA-NE": (-38.5, -12.9),
    "BRA-SE": (-46.6, -19.5),
    "BRA-S": (-51.2, -30.0),
}

############################### Addition of gas network ##########################
c_CH4, rho_CH4, capacity_CH4 = methane_capacity()
for region in regions:
    network.add(
        "Bus",
        f"gas {region}",
        carrier="gas",
        x=region_bus_coords[region][0] - 1.2,
        y=region_bus_coords[region][1] - 1.2,
    )
# Adding the network pipelines
gas_pipelines = [
    ("BRA-N", "BRA-NE"),
    ("BRA-NE", "BRA-SE"),
    ("BRA-SE", "BRA-S"),
    ("BRA-SE", "BRA-N"),
]

# Gas transport assumptions (aligned with Network model g))
gas_pipeline_efficiency = 0.995            # 0.5% loss per segment
gas_transport_marginal_cost = 0          # $/MWh_gas transported
gas_pipeline_capital_cost = 0           # $/MW-year transport capacity

for n0, n1 in gas_pipelines:
    network.add(
        "Link",
        f"gas pipeline {n0}->{n1}",
        bus0=f"gas {n0}",
        bus1=f"gas {n1}",
        p_nom=capacity_CH4,
        p_nom_extendable=False,
        carrier="gas",
        efficiency=gas_pipeline_efficiency,
        capital_cost=gas_pipeline_capital_cost,
        marginal_cost=gas_transport_marginal_cost,
    )
    network.add(
        "Link",
        f"gas pipeline {n1}->{n0}",
        bus0=f"gas {n1}",
        bus1=f"gas {n0}",
        p_nom=capacity_CH4,
        p_nom_extendable=False,
        carrier="gas",
        efficiency=gas_pipeline_efficiency,
        capital_cost=gas_pipeline_capital_cost,
        marginal_cost=gas_transport_marginal_cost,
    )

# Commodity gas supply at each regional gas bus.
# This is the source that can feed local boilers and inter-regional gas flows.

network.add(
    "Generator",
    "BRA-SE gas supply",
    bus="gas BRA-SE",
    carrier="gas",
    p_nom_extendable=True,
    p_nom=0,
    capital_cost=0.0,
    marginal_cost=marginal_cost["gas"],
)

# Addition of CCGT plants (gas -> electricity)
for region in regions:

    network.add(
        "Link",
        f"{region} gas plant",
        bus0=f"gas {region}",
        bus1=f"bus {region}",
        carrier="ccgt",

        efficiency=gas_efficiency,

        p_nom=0,
        p_nom_extendable=True,
        p_min_pu=0.0,

        capital_cost=annualized_cost("gas"),
        marginal_cost=0
    )


#%% Addition of heat sector

# Heat buses
for region in regions:
    network.add(
        "Bus",
        f"heating {region}",
        carrier="heat",
        x=region_bus_coords[region][0] + 1.2,
        y=region_bus_coords[region][1] + 1.2,
    )

# Heat pumps are added AFTER snapshots are set, so we can attach the
# time-varying COP series — see the "Heat pumps" block below.


#%% Adding generators (parameters imported from parameters.py)
# ============================
# 🔋 BATTERY PARAMETERS (UPDATED)
# ============================

battery_lifetime = 15

# CAPEX split (Li-ion typical assumption)
battery_power_cost = 65_000      # $/MW  (65 $/kW)
battery_energy_cost = 230_000    # $/MWh (230 $/kWh)

battery_eff_store = 0.95
battery_eff_dispatch = 0.95

standing_loss = 0.0005  # per hour (tuneable)

# annualised costs
power_capital_cost = annuity(battery_lifetime, 0.07) * battery_power_cost
energy_capital_cost = annuity(battery_lifetime, 0.07) * battery_energy_cost


#%% Snapshots
wind_cf_hourly.index = pd.to_datetime(wind_cf_hourly.index).tz_localize(None)
solar_cf_hourly.index = pd.to_datetime(solar_cf_hourly.index).tz_localize(None)
cop_hourly.index = pd.to_datetime(cop_hourly.index).tz_localize(None)

network.snapshots = wind_cf_hourly.index


#%% Heat pumps (electricity -> heat) with temperature-dependent COP
# COP series is precomputed per region in datapreparation.py (`cop_hourly`).
cop_per_region = {
    region: cop_hourly[region_cf_map[region]]
    .reindex(network.snapshots)
    .ffill()
    .bfill()
    for region in regions
}

for region in regions:
    network.add(
        "Link",
        f"heat pump {region}",
        carrier="heat_pump",
        bus0=f"bus {region}",
        bus1=f"heating {region}",
        efficiency=cop_per_region[region].mean(),  # placeholder; overwritten below
        p_nom=0,
        p_nom_extendable=True,
        p_min_pu=0.0,
        capital_cost=annualized_cost("heat_pump"),
        marginal_cost=marginal_cost["heat_pump"],
    )

# Attach the time-varying COP as the link's per-snapshot efficiency.
for region in regions:
    network.links_t.efficiency[f"heat pump {region}"] = cop_per_region[region].values


hydro_cap = {
    "BRA-N": max_capacity_hydro,
    "BRA-NE": max_capacity_hydro,
    "BRA-SE": max_capacity_hydro,
    "BRA-S": max_capacity_hydro,
}
biomass_cap = {
    # Keep biomass effectively uncapped here.
    # Very large p_nom_max values (e.g., 1e16) can create numerical instability.
    "BRA-N": None,
    "BRA-NE": None,
    "BRA-SE": None,
    "BRA-S": None,
}

# ============================
# GENERATORS (UNCHANGED)
# ============================

for region in regions:
    for tech in technologies:

        cap_cost = annualized_cost(tech)
        marg_cost = marginal_cost[tech]

        if tech in ["wind", "solar"]:
            CF = {"wind": wind_cf_hourly, "solar": solar_cf_hourly}[tech][region_cf_map[region]]
            p_max_pu = CF.reindex(network.snapshots).fillna(0).values
        else:
            p_max_pu = None

        p_nom_max = hydro_cap[region] if tech == "hydro" else None
        p_nom_max = biomass_cap[region] if tech == "biomass" else p_nom_max

        network.add(
            "Generator",
            f"{region} {tech}",
            bus=f"bus {region}",
            carrier=tech,
            p_nom=0,
            p_nom_extendable=True,
            p_nom_max=p_nom_max,
            capital_cost=cap_cost,
            marginal_cost=marg_cost,
            p_max_pu=p_max_pu
        )

# Gas-fired heat plants (gas -> heat) at each region
for region in regions:

    network.add(
        "Link",
        f"{region} local gas boiler",
        bus0=f"gas {region}",
        bus1=f"heating {region}",
        carrier="gas_boiler_local",

        efficiency=0.9,

        p_nom=0,
        p_nom_extendable=True,
        p_min_pu=0.0,

        capital_cost=annualized_cost("gas_boiler_local"),
        # Fuel cost is paid at "gas supply"; keep link marginal at 0 to avoid double-counting.
        marginal_cost=0.0
    )

# ============================
# 🔋 BATTERY (STORE + LINK STYLE via StorageUnit)
# ============================

for region in regions:

    network.add(
        "StorageUnit",
        f"{region} battery",
        bus=f"bus {region}",
        carrier="battery",

        p_nom_extendable=True,
        p_nom=0,

        # energy capacity implicitly = p_nom * max_hours
        max_hours=4.0,

        efficiency_store=battery_eff_store,
        efficiency_dispatch=battery_eff_dispatch,

        # standing losses (self-discharge)
        standing_loss=standing_loss,

        # IMPORTANT: split cost model
        capital_cost=power_capital_cost + energy_capital_cost,

        marginal_cost=0.0,

        cyclic_state_of_charge=True,
    )


#%% Loads (UNCHANGED)
demand = {
    "BRA-N": demand_north,
    "BRA-S": demand_south,
    "BRA-NE": demand_north_east,
    "BRA-SE": demand_south_east,
}

for region, demand_ts in demand.items():
    demand_ts = demand_ts.reindex(network.snapshots).fillna(0)

    network.add(
        "Load",
        f"load {region}",
        bus=f"bus {region}",
        p_set=demand_ts,
        overwrite=True
    )

# Add DHW heating demand at each heating bus (hourly shaped profile from datapreparation)
for region in regions:
    heat_ts = (
        dhw_heat_hourly[region_cf_map[region]]
        .reindex(network.snapshots)
        .fillna(0)
    )
    network.add(
        "Load",
        f"heat load {region}",
        bus=f"heating {region}",
        p_set=heat_ts,
        overwrite=True
    )


#%% Solve
# CO2 cap (same GlobalConstraint approach as baseModel_storage_CO2.py)
co2_limit = 5_420_000  # tCO2
network.add(
    "GlobalConstraint",
    "co2_limit",
    type="primary_energy",
    carrier_attribute="co2_emissions",
    sense="<=",
    constant=co2_limit,
)

network.optimize(
    solver_name="gurobi",
    solver_options={
        "BarHomogeneous": 1,
        "NumericFocus": 2,
    },
)

#%% Results
print("Objective value:", network.objective)
print("Total system cost:", network.statistics.system_cost())
print("Total capex:", network.statistics.capex())
print("Total opex:", network.statistics.opex())
print("\nAverage nodal prices:")
print(network.statistics.prices().mean().round(2))

# CO2 metrics (same logic style as baseModel_storage_CO2.py)
def _total_co2_emissions_t(net: pypsa.Network) -> float:
    co2_intensity = net.generators.carrier.map(net.carriers.co2_emissions).fillna(0.0)
    primary_input = net.generators_t.p.divide(net.generators.efficiency, axis=1)
    return float(primary_input.mul(co2_intensity, axis=1).sum().sum())

co2_emissions_t = _total_co2_emissions_t(network)
co2_price = float(network.global_constraints.at["co2_limit", "mu"]) if "co2_limit" in network.global_constraints.index else float("nan")

print(f"\nCO2 emissions [tCO2]: {co2_emissions_t:,.0f}")
print(f"CO2 cap [tCO2]: {co2_limit:,.0f}")
print(f"CO2 shadow price [$/tCO2]: {co2_price:,.2f}")

# Relevant annual energy statistics
elec_load_cols = network.loads.index[network.loads.index.str.startswith("load ")]
heat_load_cols = network.loads.index[network.loads.index.str.contains("heat load")]
heat_pump_cols = network.links.index[network.links.index.str.contains("heat pump")]
gas_boiler_cols = network.links.index[network.links.index.str.contains("local gas boiler")]
gas_supply_cols = network.generators.index[network.generators.index.str.contains("gas supply")]
ccgt_cols = network.links.index[network.links.index.str.contains("gas plant")]

elec_demand_mwh = float(network.loads_t.p_set.reindex(columns=elec_load_cols, fill_value=0.0).sum().sum())
heat_demand_mwh = float(network.loads_t.p_set.reindex(columns=heat_load_cols, fill_value=0.0).sum().sum())
heat_supply_hp_mwh = float((-network.links_t.p1.reindex(columns=heat_pump_cols, fill_value=0.0)).sum().sum())
heat_supply_gb_mwh = float((-network.links_t.p1.reindex(columns=gas_boiler_cols, fill_value=0.0)).sum().sum())
gas_supply_mwh = float(network.generators_t.p.reindex(columns=gas_supply_cols, fill_value=0.0).sum().sum())
gas_to_boilers_mwh = float(network.links_t.p0.reindex(columns=gas_boiler_cols, fill_value=0.0).sum().sum())
gas_to_ccgt_mwh = float(network.links_t.p0.reindex(columns=ccgt_cols, fill_value=0.0).sum().sum())
ccgt_el_mwh = float((-network.links_t.p1.reindex(columns=ccgt_cols, fill_value=0.0)).sum().sum())
ccgt_implied_efficiency = (ccgt_el_mwh / gas_to_ccgt_mwh) if gas_to_ccgt_mwh > 0 else np.nan

print("\nAnnual system statistics:")
print(pd.Series({
    "electricity_demand_TWh": elec_demand_mwh / 1e6,
    "heat_demand_TWh": heat_demand_mwh / 1e6,
    "heat_supply_heat_pump_TWh": heat_supply_hp_mwh / 1e6,
    "heat_supply_gas_boiler_TWh": heat_supply_gb_mwh / 1e6,
    "gas_supply_TWh": gas_supply_mwh / 1e6,
    "gas_to_boilers_TWh": gas_to_boilers_mwh / 1e6,
    "gas_to_ccgt_TWh": gas_to_ccgt_mwh / 1e6,
    "ccgt_generation_TWh": ccgt_el_mwh / 1e6,
    "ccgt_implied_efficiency": ccgt_implied_efficiency,
}).round(3))

print("\nKey optimal capacities [MW]:")
print("Generators:")
print(network.generators.p_nom_opt.sort_values(ascending=False).round(2))
print("\nLinks:")
print(network.links.p_nom_opt.sort_values(ascending=False).round(2))
print("\nStorage units:")
print(network.storage_units.p_nom_opt.sort_values(ascending=False).round(2))

# Quick consistency checks
heat_balance_error = abs((heat_supply_hp_mwh + heat_supply_gb_mwh) - heat_demand_mwh)
gas_balance_error = abs(gas_supply_mwh - (gas_to_boilers_mwh + gas_to_ccgt_mwh))
cap_slack = co2_limit - co2_emissions_t
print("\nConsistency checks:")
print(f"Heat balance error [MWh]: {heat_balance_error:,.2f}")
print(f"Gas balance error [MWh]: {gas_balance_error:,.2f}")
print(f"CO2 cap slack [tCO2]: {cap_slack:,.2f}")
if gas_to_ccgt_mwh > 0:
    print(f"CCGT implied efficiency [-]: {ccgt_implied_efficiency:.4f} (parameter: {gas_efficiency:.4f})")
else:
    print("CCGT implied efficiency [-]: n/a (no CCGT dispatch)")
if heat_balance_error > 1e-3:
    print("[WARN] Non-zero heat balance error; inspect heat links/signs.")
if gas_balance_error > 1e-3:
    print("[WARN] Non-zero gas balance error; inspect gas network/link dispatch.")

# %% Consolidated results tables
def _as_scalar(x):
    """Return scalar float for PyPSA statistics that may be Series/DataFrame."""
    if np.isscalar(x):
        return float(x)
    if isinstance(x, pd.DataFrame):
        return float(x.to_numpy().sum())
    if isinstance(x, pd.Series):
        return float(x.sum())
    # Fallback for array-like objects
    return float(np.asarray(x).sum())

ac_buses = network.buses.index[network.buses.carrier == "AC"]
heat_buses = network.buses.index[network.buses.carrier == "heat"]

avg_el_price = float(network.buses_t.marginal_price.reindex(columns=ac_buses, fill_value=np.nan).mean().mean())
avg_heat_price = float(network.buses_t.marginal_price.reindex(columns=heat_buses, fill_value=np.nan).mean().mean())

gas_pipeline_cols = network.links.index[network.links.index.str.contains("gas pipeline")]
elec_line_abs_flow_mwh = float(network.lines_t.p0.abs().sum().sum())
gas_pipeline_abs_flow_mwh = float(network.links_t.p0.reindex(columns=gas_pipeline_cols, fill_value=0.0).abs().sum().sum())

summary_table = pd.DataFrame(
    {
        "metric": [
            "objective_$",
            "total_system_cost_$",
            "total_capex_$",
            "total_opex_$",
            "avg_electricity_price_$_per_MWh",
            "avg_heat_price_$_per_MWh",
            "co2_emissions_t",
            "co2_cap_t",
            "co2_shadow_price_$_per_t",
            "electricity_demand_TWh",
            "heat_demand_TWh",
            "heat_supply_heat_pump_TWh",
            "heat_supply_gas_boiler_TWh",
            "gas_supply_TWh",
            "gas_to_ccgt_TWh",
            "gas_to_boilers_TWh",
            "ccgt_generation_TWh",
            "ccgt_implied_efficiency",
            "electric_line_abs_flow_TWh",
            "gas_pipeline_abs_flow_TWh",
        ],
        "value": [
            float(network.objective),
            _as_scalar(network.statistics.system_cost()),
            _as_scalar(network.statistics.capex()),
            _as_scalar(network.statistics.opex()),
            avg_el_price,
            avg_heat_price,
            co2_emissions_t,
            co2_limit,
            co2_price,
            elec_demand_mwh / 1e6,
            heat_demand_mwh / 1e6,
            heat_supply_hp_mwh / 1e6,
            heat_supply_gb_mwh / 1e6,
            gas_supply_mwh / 1e6,
            gas_to_ccgt_mwh / 1e6,
            gas_to_boilers_mwh / 1e6,
            ccgt_el_mwh / 1e6,
            ccgt_implied_efficiency,
            elec_line_abs_flow_mwh / 1e6,
            gas_pipeline_abs_flow_mwh / 1e6,
        ],
    }
)
print("\n=== Summary metrics ===")
print(summary_table.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))

# Installed capacities by technology group
gen_cap_mw = network.generators.groupby("carrier")["p_nom_opt"].sum().sort_values(ascending=False)
link_cap_mw = network.links.groupby("carrier")["p_nom_opt"].sum().sort_values(ascending=False)
store_cap_mw = network.storage_units.groupby("carrier")["p_nom_opt"].sum().sort_values(ascending=False)

capacity_table = pd.concat(
    [
        gen_cap_mw.rename("Generators_MW"),
        link_cap_mw.rename("Links_MW"),
        store_cap_mw.rename("StorageUnits_MW"),
    ],
    axis=1,
).fillna(0.0)
print("\n=== Installed capacity by carrier [MW] ===")
print(capacity_table.to_string(float_format=lambda x: f"{x:,.2f}"))

# Dispatch / throughput by technology carrier
gen_dispatch_twh = (network.generators_t.p.sum(axis=0).groupby(network.generators.carrier).sum() / 1e6).sort_values(ascending=False)
link_output_twh = (((-network.links_t.p1).clip(lower=0.0).sum(axis=0)).groupby(network.links.carrier).sum() / 1e6).sort_values(ascending=False)
store_discharge_twh = (
    network.storage_units_t.p.clip(lower=0.0).sum(axis=0).groupby(network.storage_units.carrier).sum() / 1e6
).sort_values(ascending=False)

dispatch_table = pd.concat(
    [
        gen_dispatch_twh.rename("Generators_dispatch_TWh"),
        link_output_twh.rename("Links_output_TWh"),
        store_discharge_twh.rename("Storage_discharge_TWh"),
    ],
    axis=1,
).fillna(0.0)
print("\n=== Dispatched / delivered energy by carrier [TWh] ===")
print(dispatch_table.to_string(float_format=lambda x: f"{x:,.4f}"))

# %%
network.generators.p_nom_opt # Optimal capacities of the generators
# %%
network.generators_t.p # Optimal dispatch of the generators over time
#%% # The average active power flow on the lines can now be seen
(network.lines_t.p0.mean()/1100*100).round(2)

# %%

gas_boilers = network.links[
    network.links.index.str.contains("local gas boiler")
]

print(gas_boilers[["bus0", "bus1", "p_nom_opt"]])

# %% Yearly heating supply mix (heat pump vs gas boiler)
heat_pump_links = network.links.index[network.links.index.str.contains("heat pump")]
gas_boiler_links = network.links.index[network.links.index.str.contains("local gas boiler")]

# p1 is heat output at heating bus for these links
heat_pump_supply_mwh = -network.links_t.p1.reindex(columns=heat_pump_links, fill_value=0.0).sum().sum()
gas_boiler_supply_mwh = -network.links_t.p1.reindex(columns=gas_boiler_links, fill_value=0.0).sum().sum()

heating_supply_twh = pd.Series(
    {
        "heat_pump": heat_pump_supply_mwh / 1_000_000,
        "gas_boiler": gas_boiler_supply_mwh / 1_000_000,
    }
)
heating_supply_twh = heating_supply_twh[heating_supply_twh > 0]

if heating_supply_twh.empty:
    print("[INFO] Heating supply pie chart skipped: no positive heat supply found.")
else:
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.pie(
        heating_supply_twh.values,
        labels=heating_supply_twh.index,
        colors=["orange", "brown"][:len(heating_supply_twh)],
        autopct="%1.1f%%",
        startangle=90,
        pctdistance=0.65,
        textprops={"fontsize": 11},
    )
    ax.set_title("Yearly heating supply mix")
    ax.axis("equal")
    plt.tight_layout()
    plt.show()

# %% Yearly electricity supply mix (generation + CCGT)
gen_by_carrier_total = network.generators_t.p.groupby(network.generators.carrier, axis=1).sum().sum(axis=0)
ccgt_links = network.links.index[network.links.index.str.contains("gas plant")]
ccgt_supply_total = (-network.links_t.p1.reindex(columns=ccgt_links, fill_value=0.0)).sum().sum()

elec_mix_twh = pd.Series(dtype=float)
for carrier in ["hydro", "wind", "solar", "biomass", "nuclear"]:
    elec_mix_twh.loc[carrier] = float(gen_by_carrier_total.get(carrier, 0.0)) / 1_000_000
elec_mix_twh.loc["ccgt"] = float(ccgt_supply_total) / 1_000_000
elec_mix_twh = elec_mix_twh[elec_mix_twh > 0]

if elec_mix_twh.empty:
    print("[INFO] Electricity mix pie chart skipped: no positive electricity supply found.")
else:
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.pie(
        elec_mix_twh.values,
        labels=elec_mix_twh.index,
        colors=["blue", "lightskyblue", "yellow", "green", "purple", "red"][:len(elec_mix_twh)],
        autopct="%1.1f%%",
        startangle=90,
        pctdistance=0.65,
        textprops={"fontsize": 11},
    )
    ax.set_title("Yearly electricity supply mix")
    ax.axis("equal")
    plt.tight_layout()
    plt.show()

# %% Weekly/period dispatch plots (electricity + heat)
plot_year = int(network.snapshots[0].year)
periods = {
    f"January {plot_year}": slice(f"{plot_year}-01-01", f"{plot_year}-01-31"),
    f"20-26 January {plot_year}": slice(f"{plot_year}-01-20", f"{plot_year}-01-26"),
}

for period_label, period in periods.items():
    # Electricity side: aggregate generation by carrier and include CCGT link output
    gen_by_carrier = network.generators_t.p.groupby(network.generators.carrier, axis=1).sum()
    ccgt_cols = network.links.index[network.links.index.str.contains("gas plant")]
    ccgt_el = -network.links_t.p1.reindex(columns=ccgt_cols, fill_value=0.0).sum(axis=1)

    elec_df = pd.DataFrame(index=network.snapshots)
    elec_df["hydro"] = gen_by_carrier["hydro"] if "hydro" in gen_by_carrier.columns else 0.0
    elec_df["wind"] = gen_by_carrier["wind"] if "wind" in gen_by_carrier.columns else 0.0
    elec_df["solar"] = gen_by_carrier["solar"] if "solar" in gen_by_carrier.columns else 0.0
    elec_df["biomass"] = gen_by_carrier["biomass"] if "biomass" in gen_by_carrier.columns else 0.0
    elec_df["nuclear"] = gen_by_carrier["nuclear"] if "nuclear" in gen_by_carrier.columns else 0.0
    elec_df["ccgt"] = ccgt_el
    elec_df = elec_df.loc[period]

    elec_load_cols = network.loads.index[network.loads.index.str.startswith("load ")]
    elec_demand = network.loads_t.p_set.reindex(columns=elec_load_cols, fill_value=0.0).sum(axis=1).loc[period]

    heat_pump_cols = network.links.index[network.links.index.str.contains("heat pump")]
    heat_pump_el_demand = network.links_t.p0.reindex(columns=heat_pump_cols, fill_value=0.0).sum(axis=1).loc[period]

    elec_demand_total = elec_demand + heat_pump_el_demand

    battery_cols = network.storage_units.index[network.storage_units.index.str.contains("battery")]
    battery_dispatch = network.storage_units_t.p.reindex(columns=battery_cols, fill_value=0.0).sum(axis=1).loc[period]
    elec_demand_plus_battery = elec_demand_total - battery_dispatch

    ax = elec_df.clip(lower=0).plot.area(
        figsize=(12, 4),
        linewidth=0,
        color=["blue", "lightskyblue", "yellow", "green", "purple", "red"],
    )
    elec_demand_total.plot(
        ax=ax,
        color="black",
        linewidth=1.5,
        label="el demand + heat pump el demand",
    )
    elec_demand_plus_battery.plot(
        ax=ax,
        color="black",
        linestyle="--",
        linewidth=1.5,
        label="el demand + heat pump + battery",
    )
    ax.set_ylabel("Electricity dispatch [MW]")
    ax.set_title(f"Electricity dispatch ({period_label})")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", ncol=2)
    plt.tight_layout()
    plt.show()

    # Heat side: heat pump + local gas boiler
    heat_pump_heat = -network.links_t.p1.reindex(columns=heat_pump_cols, fill_value=0.0).sum(axis=1)
    gas_boiler_cols = network.links.index[network.links.index.str.contains("local gas boiler")]
    gas_boiler_heat = -network.links_t.p1.reindex(columns=gas_boiler_cols, fill_value=0.0).sum(axis=1)

    heat_df = pd.DataFrame(
        {
            "gas boiler": gas_boiler_heat.loc[period],
            "heat pump": heat_pump_heat.loc[period],
        }
    )

    heat_load_cols = network.loads.index[network.loads.index.str.contains("heat load")]
    heat_demand = network.loads_t.p_set.reindex(columns=heat_load_cols, fill_value=0.0).sum(axis=1).loc[period]

    ax = heat_df.clip(lower=0).plot.area(
        figsize=(12, 4),
        linewidth=0,
        color=["brown", "orange"],
    )
    heat_demand.plot(
        ax=ax,
        color="black",
        linewidth=1.5,
        label="heat demand",
    )
    ax.set_ylabel("Heat dispatch [MW]")
    ax.set_title(f"Heat dispatch ({period_label})")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left")
    plt.tight_layout()
    plt.show()
# %% PLOTS
# Full-system map (electricity + gas + heat buses)
carrier_colors = {
    "AC": "tomato",
    "gas": "gray",
    "heat": "firebrick",
}
bus_colors = network.buses.carrier.map(carrier_colors).fillna("slateblue")

# Mean absolute flow per component [MW] for visual scaling on the map.
line_flow_mean = network.lines_t.p0.abs().mean(axis=0).reindex(network.lines.index).fillna(0.0)
link_flow_mean = network.links_t.p0.abs().mean(axis=0).reindex(network.links.index).fillna(0.0)

def _scaled_widths(flow_series, min_width=0.5, max_width=4.0):
    if flow_series.empty:
        return flow_series
    fmax = flow_series.max()
    if fmax <= 0:
        return pd.Series(min_width, index=flow_series.index)
    return min_width + (max_width - min_width) * (flow_series / fmax)

line_widths = _scaled_widths(line_flow_mean, min_width=0.8, max_width=5.0)
link_widths = _scaled_widths(link_flow_mean, min_width=0.5, max_width=3.5)

fig, ax = plt.subplots(figsize=(11, 10), subplot_kw={"projection": ccrs.PlateCarree()})
ax.set_extent([-75, -30, -35, 7], crs=ccrs.PlateCarree())
ax.add_feature(cfeature.LAND, facecolor="whitesmoke")
ax.add_feature(cfeature.OCEAN, facecolor="lightcyan")
ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
ax.add_feature(cfeature.BORDERS, linewidth=0.5, linestyle="--")
ax.add_feature(cfeature.STATES, linewidth=0.3, edgecolor="gray")

network.plot(
    ax=ax,
    bus_sizes=0.05,
    bus_colors=bus_colors,
    line_colors="steelblue",
    line_widths=line_widths,
    link_colors="darkorange",
    link_widths=link_widths,
    title="Integrated electricity-gas-heat network (flow-scaled widths)",
)
plt.tight_layout()
plt.show()


def _join_items(items):
    items = sorted(set(items))
    return ", ".join(items) if items else "-"


# Overview table of all buses, their connections, components, and carriers
overview_rows = []
for bus_name, bus in network.buses.iterrows():
    connected_lines = []
    if not network.lines.empty:
        line_mask = (network.lines.bus0 == bus_name) | (network.lines.bus1 == bus_name)
        connected_lines = network.lines.index[line_mask].tolist()

    links_out = []
    links_in = []
    if not network.links.empty:
        links_out = network.links.index[network.links.bus0 == bus_name].tolist()
        links_in = network.links.index[network.links.bus1 == bus_name].tolist()

    generators_here = []
    if not network.generators.empty:
        gens = network.generators[network.generators.bus == bus_name]
        generators_here = [f"{idx} ({row.carrier})" for idx, row in gens.iterrows()]

    loads_here = []
    if not network.loads.empty:
        loads_here = network.loads.index[network.loads.bus == bus_name].tolist()

    storage_here = []
    if not network.storage_units.empty:
        stores = network.storage_units[network.storage_units.bus == bus_name]
        storage_here = [f"{idx} ({row.carrier})" for idx, row in stores.iterrows()]

    overview_rows.append(
        {
            "bus": bus_name,
            "bus_carrier": bus.carrier,
            "connected_lines": _join_items(connected_lines),
            "links_out (bus0->bus1)": _join_items(links_out),
            "links_in (bus0->bus1)": _join_items(links_in),
            "generators (carrier)": _join_items(generators_here),
            "loads": _join_items(loads_here),
            "storage_units (carrier)": _join_items(storage_here),
        }
    )

system_overview = (
    pd.DataFrame(overview_rows)
    .sort_values(["bus_carrier", "bus"])
    .reset_index(drop=True)
)
print("\n=== System overview by bus ===")
print(system_overview.to_string(index=False))



#%%############################ System overview table ####################################

import pandas as pd

# =========================
# SETTINGS
# =========================

region = "BRA-SE"

bus = f"bus {region}"
gas_bus = f"gas {region}"
heat_bus = f"heating {region}"

techs = ["hydro", "biomass", "nuclear", "wind", "solar"]

gen_cap = {}
gen_disp = {}

# =========================
# 1. GENERATION (AC BUS)
# =========================

for tech in techs:

    gens = network.generators.index[
        (network.generators.carrier == tech) &
        (network.generators.bus == bus)
    ]

    if len(gens) > 0:
        gen_cap[tech] = network.generators.p_nom_opt[gens].sum()

        # FIX: remove duplicate column selection
        gen_disp[tech] = network.generators_t.p[gens].sum().sum()
    else:
        gen_cap[tech] = 0.0
        gen_disp[tech] = 0.0


# =========================
# 2. CCGT (gas -> electricity)
# =========================

ccgt_links = network.links.index[
    (network.links.carrier == "ccgt") &
    (network.links.bus1 == bus)
]

gen_cap["ccgt"] = network.links.p_nom_opt[ccgt_links].sum()

# electricity output is p1 (negative sign)
gen_disp["ccgt"] = (-network.links_t.p1[ccgt_links]).sum().sum()


# =========================
# 3. TOTAL GENERATION
# =========================

gen_cap_total = sum(gen_cap.values())
gen_disp_total = sum(gen_disp.values())

gen_cap_share = {
    k: 100 * gen_cap[k] / gen_cap_total if gen_cap_total > 0 else 0
    for k in gen_cap
}

gen_disp_share = {
    k: 100 * gen_disp[k] / gen_disp_total if gen_disp_total > 0 else 0
    for k in gen_disp
}


# =========================
# 4. BATTERY
# =========================

battery_units = network.storage_units.index[
    (network.storage_units.bus == bus) &
    (network.storage_units.carrier == "battery")
]

battery_capacity = network.storage_units.p_nom_opt[battery_units].sum()

battery_dispatch = network.storage_units_t.p_dispatch[battery_units].sum().sum()
battery_charge = network.storage_units_t.p_store[battery_units].sum().sum()

battery_net = battery_dispatch - battery_charge


# =========================
# 5. NET ELECTRICITY TRANSFER
# =========================

net_elec = 0.0

for line in network.lines.index:

    flow = network.lines_t.p0[line]
    bus0 = network.lines.loc[line, "bus0"]
    bus1 = network.lines.loc[line, "bus1"]

    if bus1 == bus:
        net_elec += flow.sum()

    if bus0 == bus:
        net_elec -= flow.sum()


# =========================
# 6. NET GAS TRANSFER
# =========================

net_gas = 0.0

gas_links = network.links.index[
    network.links.index.str.contains("gas pipeline")
]

for link in gas_links:

    flow = network.links_t.p0[link]
    bus0 = network.links.loc[link, "bus0"]
    bus1 = network.links.loc[link, "bus1"]

    if bus1 == gas_bus:
        net_gas += flow.sum()

    if bus0 == gas_bus:
        net_gas -= flow.sum()


# =========================
# 7. HEAT GENERATION (NEW)
# =========================

heat_links = network.links.index[
    network.links.bus1 == heat_bus
]

heat_dispatch = network.links_t.p1[heat_links].sum().sum()


# =========================
# 8. SHARES
# =========================

battery_capacity_share = 100 * battery_capacity / gen_cap_total if gen_cap_total > 0 else 0
battery_dispatch_share = 100 * battery_net / gen_disp_total if gen_disp_total > 0 else 0

net_elec_share = 100 * net_elec / gen_disp_total if gen_disp_total > 0 else 0
net_gas_share = 100 * net_gas / gen_disp_total if gen_disp_total > 0 else 0


# =========================
# 9. GENERATION TABLE
# =========================

table = pd.DataFrame({
    "Technology": list(gen_disp_share.keys()),
    "Capacity (%)": [gen_cap_share[k] for k in gen_disp_share.keys()],
    "Dispatch (%)": [gen_disp_share[k] for k in gen_disp_share.keys()]
})

print("\n=== GENERATION MIX (100% BASE) ===\n")
print(table)


# =========================
# 10. SYSTEM COMPONENTS
# =========================

print("\n=== SYSTEM COMPONENTS ===\n")

print(f"Battery capacity (MW): {battery_capacity:.2f}")
print(f"Battery capacity share: {battery_capacity_share:.2f}%")

print(f"Battery net dispatch (MWh): {battery_net:.2f}")
print(f"Battery dispatch share: {battery_dispatch_share:.2f}%")

print(f"Net electricity flow (MWh): {net_elec:.2f}")
print(f"Net electricity share: {net_elec_share:.2f}%")

print(f"Net gas flow (MWh): {net_gas:.2f}")
print(f"Net gas share: {net_gas_share:.2f}%")

print(f"Total heat supplied (MWh): {heat_dispatch:.2f}")
# %%
network.links_t.p0.abs().sum()
# %%
