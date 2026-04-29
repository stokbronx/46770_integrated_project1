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
    wind_cf_hourly, solar_cf_hourly, cop_hourly,
)
import importlib
import parameters
importlib.reload(parameters)
from parameters import (
    capital_cost, opex_cost, marginal_cost, lifetime,
    max_capacity_hydro, annuity, annualized_cost, DISCOUNT_RATE, methane_capacity,
)
#%% Adding the buses to the network
network = pypsa.Network()

network.add(
    "Carrier",
    ["hydro", "biomass", "nuclear", "wind", "solar", "battery", "gas", "heat", "heat_pump", "gas_boiler"],
    nice_name=["Hydro", "Biomass", "Nuclear", "Wind", "Solar", "Battery", "Gas", "Heat", "Heat pump", "Gas boiler"],
    color=["aquamarine", "sienna", "purple", "dodgerblue", "gold", "violet", "gray", "red", "orange", "brown"]
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

############################### Addition of hydrogen pipelines ##########################
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

for n0, n1 in gas_pipelines:
    network.add(
        "Link",
        f"gas pipeline {n0}-{n1}",
        bus0=f"gas {n0}",
        bus1=f"gas {n1}",
        p_nom=0,
        p_nom_extendable=True,
        carrier="gas",
        efficiency=1.0,
        marginal_cost=0.0
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

# Gas-fired heat plants (gas -> heat) at each region
for region in regions:

    network.add(
        "Link",
        f"{region} gas heat plant",
        bus0=f"gas {region}",
        bus1=f"heating {region}",
        carrier="gas_boiler",

        efficiency=0.9,

        p_nom=0,
        p_nom_extendable=True,

        capital_cost=annualized_cost("gas"),
        marginal_cost=marginal_cost["gas"]
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

# Add heating demand at each heating bus (fraction of regional electricity demand)
heat_demand_share = 0.35
for region, demand_ts in demand.items():
    heat_ts = (heat_demand_share * demand_ts).reindex(network.snapshots).fillna(0)
    network.add(
        "Load",
        f"heat load {region}",
        bus=f"heating {region}",
        p_set=heat_ts,
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
    network.links.index.str.contains("gas heat plant")
]

print(gas_plants[["bus0", "bus1", "p_nom_opt"]])
# %% PLOTS
# Full-system map (electricity + gas + heat buses)
carrier_colors = {
    "AC": "tomato",
    "gas": "gray",
    "heat": "firebrick",
}
bus_colors = network.buses.carrier.map(carrier_colors).fillna("slateblue")

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
    line_widths=2.5,
    link_colors="darkorange",
    link_widths=1.8,
    title="Integrated electricity-gas-heat network",
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
