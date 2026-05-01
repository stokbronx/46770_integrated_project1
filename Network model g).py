#%%
from tkinter import SE

import pandas as pd
#pd.options.mode.string_storage = "python"
import numpy as np
import pypsa
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from datapreparation import (
    demand_north, demand_south, demand_north_east, demand_south_east,
    wind_cf_hourly, solar_cf_hourly,)
import importlib
import parameters
importlib.reload(parameters)
from parameters import (
    capital_cost, opex_cost, marginal_cost, lifetime,
    max_capacity_hydro, annuity, annualized_cost, DISCOUNT_RATE,methane_capacity, gas_efficiency
)


#%% Adding the buses to the network
network = pypsa.Network()

network.add(
    "Carrier",
    ["hydro", "biomass", "nuclear", "wind", "solar", "battery", "H2", "gas", "ccgt"],
    nice_name=["Hydro", "Biomass", "Nuclear", "Wind", "Solar", "Battery", "Hydrogen", "Gas", "CCGT"],
    color=["aquamarine", "sienna", "purple", "dodgerblue", "gold", "violet", "green", "gray", "dimgray"]
)
network.add("Carrier", "AC")


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

#%%############################## Addition of gas pipelines ##########################
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

# Gas transport assumptions (keep these small to avoid over-penalizing transport)
gas_pipeline_efficiency = 0.995            # 0.5% loss per transport segment
gas_transport_marginal_cost = 0        # $/MWh_gas transported
gas_pipeline_capital_cost = 0           # $/MW-year for transport capacity

for n0, n1 in gas_pipelines:
    network.add(
        "Link",
        f"gas pipeline {n0}->{n1}",
        bus0=f"gas {n0}",
        bus1=f"gas {n1}",
        p_nom=capacity_CH4,
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
        p_nom=0,
        p_nom_extendable=True,
        carrier="gas",
        efficiency=gas_pipeline_efficiency,
        capital_cost=gas_pipeline_capital_cost,
        marginal_cost=gas_transport_marginal_cost,
    )

# Gas commodity supply at each regional gas bus
network.add(
    "Generator",
    "BRA-SE gas supply",
    bus="gas BRA-SE",
    carrier="gas",
    p_nom=0,
    p_nom_extendable=True,
    capital_cost=0.0,
    marginal_cost=gas_efficiency * marginal_cost["gas"],
)
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

network.snapshots = wind_cf_hourly.index


hydro_cap = {
    "BRA-N": max_capacity_hydro,
    "BRA-NE": max_capacity_hydro,
    "BRA-SE": max_capacity_hydro,
    "BRA-S": max_capacity_hydro,
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

        capital_cost=annualized_cost("gas"),
        marginal_cost=0
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


#%% Solve
network.optimize(solver_name="gurobi")

#%% Results
print("Objective value:", network.objective)
print("Total system cost:", network.statistics.system_cost())
print("Total capex:", network.statistics.capex())
print("Total opex:", network.statistics.opex())
network.statistics.prices()

# %%
network.generators.p_nom_opt # Optimal capacities of the generators
# %%
network.generators_t.p # Optimal dispatch of the generators over time
#%% # The average active power flow on the lines can now be seen
(network.lines_t.p0.mean()/1100*100).round(2)

# %%

gas_plants = network.links[
    network.links.index.str.contains("gas plant")
]

print(gas_plants[["bus0", "bus1", "p_nom_opt"]])

# %% Plots: network transport and dispatch
# 1) Hourly total transported electricity vs gas in the network
elec_transport_hourly = network.lines_t.p0.abs().sum(axis=1)
gas_pipeline_cols = network.links.index[network.links.index.str.contains("gas pipeline")]
gas_transport_hourly = (
    network.links_t.p0.reindex(columns=gas_pipeline_cols, fill_value=0.0).abs().sum(axis=1)
)

plt.figure(figsize=(12, 4))
plt.plot(elec_transport_hourly.index, elec_transport_hourly.values, label="Electricity transport (lines)", color="royalblue", linewidth=1.1)
plt.plot(gas_transport_hourly.index, gas_transport_hourly.values, label="Gas transport (pipelines)", color="dimgray", linewidth=1.1)
plt.title("Hourly transported energy in electricity and gas network")
plt.xlabel("Time")
plt.ylabel("Transported power (MW)")
plt.grid(alpha=0.3)
plt.legend()
plt.tight_layout()
plt.show()

# 2) Electricity mix (including CCGT link output)
gen_by_carrier = (
    network.generators_t.p.groupby(network.generators.carrier, axis=1).sum()
)
ccgt_cols = network.links.index[network.links.index.str.contains("gas plant")]
ccgt_output = -network.links_t.p1.reindex(columns=ccgt_cols, fill_value=0.0).sum(axis=1)  # bus1 electricity output

tech_colors = {
    "hydro": "blue",
    "solar": "yellow",
    "biomass": "green",
    "nuclear": "purple",
    "wind": "lightskyblue",
    "ccgt": "red",
}

mix_df = gen_by_carrier.copy()
mix_df["ccgt"] = ccgt_output
mix_df = mix_df[[c for c in tech_colors.keys() if c in mix_df.columns]]
annual_mix_twh = mix_df.sum().sort_values(ascending=False) / 1_000_000
annual_mix_twh = annual_mix_twh[annual_mix_twh > 0]

if annual_mix_twh.empty:
    print("[INFO] Electricity mix pie chart skipped: no positive generation in results.")
else:
    fig, ax = plt.subplots(figsize=(9, 7))
    min_pct_label = 2.0
    def _autopct_threshold(pct):
        return f"{pct:.1f}%" if pct >= min_pct_label else ""

    wedges, _, autotexts = ax.pie(
        annual_mix_twh.values,
        labels=None,
        colors=[tech_colors[c] for c in annual_mix_twh.index],
        autopct=_autopct_threshold,
        startangle=90,
        pctdistance=0.63,
        textprops={"fontsize": 11},
    )
    for txt in autotexts:
        txt.set_color("black")
        txt.set_fontsize(11)

    ax.set_title("Annual electricity mix (including CCGT)", fontsize=15, pad=18)
    ax.legend(
        wedges,
        [f"{tech} ({val:.1f}%)" for tech, val in zip(annual_mix_twh.index, annual_mix_twh.values / annual_mix_twh.values.sum() * 100)],
        title="Technology",
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        frameon=True,
    )
    ax.axis("equal")
    fig.subplots_adjust(top=0.88, right=0.78)
    plt.show()

# 3) Hourly dispatch in network including CCGT (one week in January)
dispatch_order = ["hydro", "solar", "biomass", "nuclear", "wind", "ccgt"]
dispatch_cols = [c for c in dispatch_order if c in mix_df.columns]
dispatch_df = mix_df[dispatch_cols].clip(lower=0)
january_dispatch = dispatch_df.loc[dispatch_df.index.month == 1]
week_dispatch = january_dispatch.iloc[:24 * 7]

if week_dispatch.empty or week_dispatch.sum().sum() <= 0:
    print("[INFO] Dispatch stackplot skipped: no positive dispatch in selected January week.")
else:
    plt.figure(figsize=(13, 5))
    plt.stackplot(
        week_dispatch.index,
        [week_dispatch[c].values for c in week_dispatch.columns],
        labels=list(week_dispatch.columns),
        colors=[tech_colors[c] for c in week_dispatch.columns],
        alpha=0.9,
    )
    week_start = week_dispatch.index.min()
    week_end = week_dispatch.index.max()
    plt.title(f"Hourly electricity dispatch by technology (incl. CCGT) - January week ({week_start.date()} to {week_end.date()})")
    plt.xlabel("Time")
    plt.ylabel("Dispatch (MW)")
    plt.legend(loc="upper left", ncol=3)
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.show()

# 4) Electricity network map (style from model d)
bus_labels = {
    "bus BRA-N": "N",
    "bus BRA-NE": "NE",
    "bus BRA-SE": "SE",
    "bus BRA-S": "S",
}

# Total annual electricity generation per AC bus (MWh), incl. CCGT output
gen_per_bus = network.generators_t.p.sum().groupby(network.generators.bus).sum()
ccgt_links = network.links[network.links.index.str.contains("gas plant")]
ccgt_per_link = -network.links_t.p1.reindex(columns=ccgt_links.index, fill_value=0.0).sum(axis=0)
for link_name, bus_name in ccgt_links["bus1"].items():
    gen_per_bus.loc[bus_name] = gen_per_bus.get(bus_name, 0.0) + ccgt_per_link.get(link_name, 0.0)

# Total gas converted in CCGT per electricity bus (MWh_gas input)
ccgt_gas_input_per_link = network.links_t.p0.reindex(columns=ccgt_links.index, fill_value=0.0).sum(axis=0)
ac_buses = [b for b in network.buses.index if b.startswith("bus ")]
gas_to_power_per_bus = pd.Series(0.0, index=ac_buses)
for link_name, bus_name in ccgt_links["bus1"].items():
    gas_to_power_per_bus.loc[bus_name] = gas_to_power_per_bus.get(bus_name, 0.0) + ccgt_gas_input_per_link.get(link_name, 0.0)

gen_per_bus = gen_per_bus.reindex(ac_buses, fill_value=0.0)
bus_sizes = (gen_per_bus / max(gen_per_bus.max(), 1e-9)) * 0.15

# Electricity line flow metrics
line_net_flow = network.lines_t.p0.sum()
line_abs_flow = network.lines_t.p0.abs().sum()
line_widths = 1.5 + (line_abs_flow / max(line_abs_flow.max(), 1e-9)) * (10 - 1.5)

fig, ax = plt.subplots(figsize=(10, 10), subplot_kw={"projection": ccrs.PlateCarree()})
ax.set_extent([-75, -30, -35, 7], crs=ccrs.PlateCarree())
ax.add_feature(cfeature.LAND, facecolor="whitesmoke")
ax.add_feature(cfeature.OCEAN, facecolor="lightcyan")
ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
ax.add_feature(cfeature.BORDERS, linewidth=0.5, linestyle="--")
ax.add_feature(cfeature.STATES, linewidth=0.3, edgecolor="gray")

# Electricity network base style via PyPSA plot
network.plot(
    ax=ax,
    bus_sizes=bus_sizes,
    line_widths=line_widths,
    margin=0.2,
    bus_colors="tomato",
    line_colors="steelblue",
    title="Brazilian Power Network",
)

# Annotate AC buses with yearly generation
for bus_name, label in bus_labels.items():
    bx = network.buses.loc[bus_name, "x"]
    by = network.buses.loc[bus_name, "y"]
    prod_twh = gen_per_bus.get(bus_name, 0.0) / 1e6
    gas_conv_twh = gas_to_power_per_bus.get(bus_name, 0.0) / 1e6
    ax.annotate(
        f"Generation: {label}\nElectricity: {prod_twh:.1f} TWh\nGas: {gas_conv_twh:.1f} TWh",
        xy=(bx, by),
        xytext=(15, 15),
        textcoords="offset points",
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray", alpha=0.85),
        transform=ccrs.PlateCarree(),
    )

# Annotate electricity lines with directional yearly net flow
line_label_offsets = {
    " line N-NE":  (0, 12),
    " line NE-SE": (12, 0),
    " line SE-S":  (12, 0),
    " line SE-N":  (-14, -10),
}
for line_name in network.lines.index:
    bus0 = network.lines.loc[line_name, "bus0"]
    bus1 = network.lines.loc[line_name, "bus1"]
    net = line_net_flow.get(line_name, 0.0)
    x0, y0 = network.buses.loc[bus0, ["x", "y"]]
    x1, y1 = network.buses.loc[bus1, ["x", "y"]]
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    if net >= 0:
        arrow = f"{bus_labels[bus0]}->{bus_labels[bus1]}"
    else:
        arrow = f"{bus_labels[bus1]}->{bus_labels[bus0]}"
        net = -net
    flow_twh = net / 1e6
    ox, oy = line_label_offsets.get(line_name, (0, 0))
    ax.annotate(
        f"{arrow}  {flow_twh:.1f} TWh",
        xy=(mx, my),
        xytext=(ox, oy),
        textcoords="offset points",
        fontsize=9,
        ha="center",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="lightyellow", edgecolor="gray", alpha=0.9),
        transform=ccrs.PlateCarree(),
    )

plt.tight_layout()
plt.show()

#%%
import pandas as pd

# =========================
# SETTINGS
# =========================

region = "BRA-SE"
bus = f"bus {region}"
gas_bus = f"gas {region}"

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
        gen_disp[tech] = network.generators_t.p[gens].loc[:, gens].sum().sum()
    else:
        gen_cap[tech] = 0.0
        gen_disp[tech] = 0.0


# =========================
# 2. CCGT (electricity output)
# =========================

ccgt_links = network.links.index[
    (network.links.carrier == "ccgt") &
    (network.links.bus1 == bus)
]

gen_cap["ccgt"] = network.links.p_nom_opt[ccgt_links].sum()
gen_disp["ccgt"] = (-network.links_t.p1[ccgt_links]).sum().sum()


# =========================
# 3. TOTAL GENERATION (100%)
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
# 4. BATTERY (SEPARATE)
# =========================

battery_units = network.storage_units.index[
    network.storage_units.bus == bus
]

battery_capacity = network.storage_units.p_nom_opt[battery_units].sum()

battery_dispatch = network.storage_units_t.p_dispatch[battery_units].sum().sum()
battery_charge = network.storage_units_t.p_store[battery_units].sum().sum()

battery_net = battery_dispatch - battery_charge


# =========================
# 5. NET ELECTRICITY TRANSFER (CORRECT SIGNED FLOW)
# =========================

net_elec = 0.0

for line in network.lines.index:

    flow = network.lines_t.p0[line]
    bus0 = network.lines.loc[line, "bus0"]
    bus1 = network.lines.loc[line, "bus1"]

    # INTO BRA-SE
    if bus1 == bus:
        net_elec += flow.sum()

    # OUT OF BRA-SE
    if bus0 == bus:
        net_elec -= flow.sum()


# =========================
# 6. NET GAS TRANSFER (CORRECT SIGNED FLOW)
# =========================

net_gas = 0.0

gas_links = network.links.index[
    network.links.index.str.contains("gas pipeline")
]

for link in gas_links:

    flow = network.links_t.p0[link]
    bus0 = network.links.loc[link, "bus0"]
    bus1 = network.links.loc[link, "bus1"]

    # INTO gas system of BRA-SE
    if bus1 == gas_bus:
        net_gas += flow.sum()

    # OUT of gas system of BRA-SE
    if bus0 == gas_bus:
        net_gas -= flow.sum()


# =========================
# 7. PERCENTAGES
# =========================

battery_capacity_share = 100 * battery_capacity / gen_cap_total if gen_cap_total > 0 else 0
battery_dispatch_share = 100 * battery_net / gen_disp_total if gen_disp_total > 0 else 0

net_elec_share = 100 * net_elec / gen_disp_total if gen_disp_total > 0 else 0
net_gas_share = 100 * net_gas / gen_disp_total if gen_disp_total > 0 else 0


# =========================
# 8. FINAL TABLE (GENERATION = 100%)
# =========================

table = pd.DataFrame({
    "Technology": list(gen_disp_share.keys()),
    "Capacity (%)": [gen_cap_share[k] for k in gen_disp_share.keys()],
    "Dispatch (%)": [gen_disp_share[k] for k in gen_disp_share.keys()]
})

print("\n=== GENERATION MIX (100% BASE) ===\n")
print(table)


# =========================
# 9. SYSTEM COMPONENTS
# =========================

print("\n=== SYSTEM COMPONENTS (NET FLOWS) ===\n")

print(f"Battery capacity (MW): {battery_capacity:.2f}")
print(f"Battery capacity share: {battery_capacity_share:.2f}%")

print(f"Battery net dispatch (MWh): {battery_net:.2f}")
print(f"Battery dispatch share: {battery_dispatch_share:.2f}%")

print(f"Net electricity flow (MWh): {net_elec:.2f}")
print(f"Net electricity share: {net_elec_share:.2f}%")

print(f"Net gas flow (MWh): {net_gas:.2f}")
print(f"Net gas share: {net_gas_share:.2f}%")
#%%
(network.lines_t.p0.mean()/1100*100).round(2)
# %%
(network.links_t.p0.mean()/1100*100).round(2)

# %%
#%%
print((network.lines_t.p0.mean()).round(2))

print((network.links_t.p0.mean()).round(2))
# %%
network.lines_t.p0.abs().sum()
# %%
network.links_t.p0.abs().sum()
# %%
print(22.96/(network.generators_t.p.sum().sum()/10**6))
# %%
