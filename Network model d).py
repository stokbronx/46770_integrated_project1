#%% # loading of data and libraries
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

#%% Adding the buses to the network
network = pypsa.Network()

network.add(
    "Carrier",
    ["hydro", "biomass", "nuclear", "wind", "solar"],
    nice_name=["Hydro", "Biomass", "Nuclear", "Wind", "Solar"],
    color=["aquamarine", "sienna", "purple", "dodgerblue", "gold"]
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
network.buses

# Adding the network lines between the buses
network.add("Line"," line N-NE", bus0 = "bus BRA-N", bus1= "bus BRA-NE", x=0.1, r=0.01, carrier="AC",s_nom=1100) 
network.add("Line"," line NE-SE", bus0 = "bus BRA-NE", bus1= "bus BRA-SE", x=0.1, r=0.01, carrier="AC",s_nom=1100)
network.add("Line"," line SE-S", bus0 = "bus BRA-SE", bus1= "bus BRA-S", x=0.1, r=0.01, carrier="AC",s_nom=1100)
network.add("Line"," line SE-N", bus0 = "bus BRA-SE", bus1= "bus BRA-N", x=0.1, r=0.01, carrier="AC",s_nom=1100)
# network.add("Line"," line S-NE", bus0 = "bus BRA-S", bus1= "bus BRA-NE", x=0.1, r=0.01, carrier="AC",s_nom=1100)
# x is the reactance, r is the resistance(In actuality equal to zero), s_nom is the nominal apparent power in VA

# %% Adding the generators to the network
"""power_plants = { 
    "BRA": {"hydro": 110000, "biomass": 46500, "nuclear": 2000, "wind": 29500, "solar": 48500},
} #####These capacities needs to be changed when the optimal values are found############

share = { #####These shares needs to be changed when the optimal values are found############
    "BRA-N": {"hydro": 0.1, "biomass": 0.2, "nuclear": 0.3, "wind": 0.4, "solar": 0.5},
    "BRA-S": {"hydro": 0.6, "biomass": 0.7, "nuclear": 0.8, "wind": 0.9, "solar": 1.0},
    "BRA-NE": {"hydro": 0.1, "biomass": 0.2, "nuclear": 0.3, "wind": 0.4, "solar": 0.5},
    "BRA-SE": {"hydro": 0.9, "biomass": 0.7, "nuclear": 0.8, "wind": 0.9, "solar": 1.0},
}
# Total Brazilian capacities
"""
# lifetime of the technologies
tech_lifetime = {
    "hydro": 65,
    "biomass": 25,
    "nuclear": 50,
    "wind": 25,
    "solar": 25,
}
# Add costs
#%% MODEL PARAMETERS

capital_cost = dict(
    hydro=3750000, # $/MW
    #gas=1000,
    #coal=1000,
    biomass=3750000, # $/MW
    nuclear=7500000, # $/MW
    wind=2100000, # $/MW (onshore)
    solar=1250000, # $/MW
)

#JOINT CAPACITY AND DISPATCH OPTIMIZATION (NOMINAL CAPACITY IS A DECISION VARIABLE, NOT FIXED)

#MARGINAL COSTS (Needs to be updated with data from litterature)
marginal_cost = dict(
    hydro=3, # $/MWh
    #gas=1000,
    #coal=100,
    biomass=75, # $/MWh
    nuclear=12, # $/MWh 
    wind=0, # $/MWh
    solar=0, # $/MWh
)
#%% The annuity function is defined

def annuity(n,r):
    """ Calculate the annuity factor for an asset with lifetime n years and
    discount rate  r """

    if r > 0:
        return r/(1. - 1./(1.+r)**n)
    else:
        return 1/n

#%% Mapping from network region names to CF DataFrame columns
# Fix timestamps
# Convert index to datetime
wind_cf_hourly.index = pd.to_datetime(wind_cf_hourly.index).tz_localize(None)
solar_cf_hourly.index = pd.to_datetime(solar_cf_hourly.index).tz_localize(None)

# Set network snapshots
network.snapshots = wind_cf_hourly.index
# Set snapshots
network.snapshots = wind_cf_hourly.index
region_cf_map = {
    "BRA-N": "N",
    "BRA-S": "S",
    "BRA-NE": "NE",
    "BRA-SE": "SE"
}
technologies = ["hydro", "biomass", "nuclear", "wind", "solar"]
regions = ["BRA-N", "BRA-NE", "BRA-SE", "BRA-S"]
hydro_cap = { # Introduction a max capacity on hydro power
    "BRA-N": 40000, # MW
    "BRA-NE": 40000,
    "BRA-SE": 40000,
    "BRA-S": 40000
}
network.snapshots = pd.to_datetime(wind_cf_hourly.index).tz_localize(None)
for region in regions:
    for tech in technologies:

        lifetime = tech_lifetime[tech]
        cap_cost = annuity(lifetime, 0.07) * capital_cost[tech] * (1 + 0.033)
        marg_cost = marginal_cost[tech]

        if tech in ["wind", "solar"]:
            CF = {"wind": wind_cf_hourly, "solar": solar_cf_hourly}[tech][region_cf_map[region]]
            p_max_pu = CF.reindex(network.snapshots).fillna(0).values
        else:
            p_max_pu = None

        # Hydro capacity constraint
        if tech == "hydro":
            p_nom_max = hydro_cap[region]
        else:
            p_nom_max = None

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
# %% Now the loads are added to the network

demand = {
    "BRA-N": demand_north,
    "BRA-S": demand_south,
    "BRA-NE": demand_north_east,
    "BRA-SE": demand_south_east,
}


#%% ADD LOADS TO NETWORK
for region, demand_ts in demand.items():
    demand_ts = demand_ts.reindex(network.snapshots).fillna(0)

    print(f"\nDEBUG {region}:")
    print("  NaNs:", demand_ts.isna().sum())
    print("  Sum:", demand_ts.sum())

    network.add(
        "Load",
        f"load {region}",
        bus=f"bus {region}",
        p_set=demand_ts,
        overwrite=True
    )

#%%
print("Demand timestamps:", demand_north.index[:10])
print("Snapshot timestamps:", network.snapshots[:10])

# %%
def fix_string_columns(df):
    for col in df.columns:
        if pd.api.types.is_string_dtype(df[col]):
            df[col] = df[col].astype("object")

# Apply to all relevant PyPSA component tables
for table in [
    network.buses,
    network.lines,
    network.generators,
    network.loads,
    network.carriers,
    network.links,
]:
    fix_string_columns(table)



# %%
network.optimize(solver_name="gurobi")

# %%
print("Objective value:", network.objective)
print("Total system cost:", network.statistics.system_cost())
print("Total capex:", network.statistics.capex())
print("Total opex:", network.statistics.opex())

# %%
network.generators.p_nom_opt # Optimal capacities of the generators
# %%
network.generators_t.p # Optimal dispatch of the generators over time
#%% 
network.lines_t.p0.sum() # The active power flow on the lines can now be seen

# %% ###########################3 Plotting of the network ############################


bus_labels = {
    "bus BRA-N": "N",
    "bus BRA-NE": "NE",
    "bus BRA-SE": "SE",
    "bus BRA-S": "S",
}

# Total annual production per bus (MWh)
gen_per_bus = network.generators_t.p.sum().groupby(network.generators.bus).sum()

# Bus sizes proportional to total production, scaled for visibility
bus_sizes = gen_per_bus / gen_per_bus.max() * 0.15

# Net annual energy flow per line (MWh); positive = bus0 → bus1
line_net_flow = network.lines_t.p0.sum()
line_abs_flow = network.lines_t.p0.abs().sum()

# Line widths proportional to absolute transported energy
lw_min, lw_max = 1.5, 10
line_widths = lw_min + (line_abs_flow / line_abs_flow.max()) * (lw_max - lw_min)

fig, ax = plt.subplots(figsize=(10, 10), subplot_kw={"projection": ccrs.PlateCarree()})
ax.set_extent([-75, -30, -35, 7], crs=ccrs.PlateCarree())
ax.add_feature(cfeature.LAND, facecolor="whitesmoke")
ax.add_feature(cfeature.OCEAN, facecolor="lightcyan")
ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
ax.add_feature(cfeature.BORDERS, linewidth=0.5, linestyle="--")
ax.add_feature(cfeature.STATES, linewidth=0.3, edgecolor="gray")

network.plot(
    ax=ax,
    bus_sizes=bus_sizes,
    line_widths=line_widths,
    margin=0.2,
    bus_colors="tomato",
    line_colors="steelblue",
    title="Brazilian Power Network",
)

# Annotate each bus with its name and annual production
for bus_name, label in bus_labels.items():
    bx = network.buses.loc[bus_name, "x"]
    by = network.buses.loc[bus_name, "y"]
    prod_twh = gen_per_bus[bus_name] / 1e6
    ax.annotate(
        f"{label}\n{prod_twh:.1f} TWh",
        xy=(bx, by),
        xytext=(15, 15),
        textcoords="offset points",
        fontsize=11,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray", alpha=0.85),
        transform=ccrs.PlateCarree(),
    )

# Annotate each line with directional energy flow
label_offsets = {
    " line N-NE":  (0, 12),
    " line NE-SE": (12, 0),
    " line SE-S":  (12, 0),
    " line SE-N":  (-14, -10),
    " line S-NE":  (-14, 10),
}

for line_name in network.lines.index:
    bus0 = network.lines.loc[line_name, "bus0"]
    bus1 = network.lines.loc[line_name, "bus1"]
    net = line_net_flow[line_name]

    x0, y0 = network.buses.loc[bus0, "x"], network.buses.loc[bus0, "y"]
    x1, y1 = network.buses.loc[bus1, "x"], network.buses.loc[bus1, "y"]
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2

    if net >= 0:
        arrow = f"{bus_labels[bus0]}\u2192{bus_labels[bus1]}"
    else:
        arrow = f"{bus_labels[bus1]}\u2192{bus_labels[bus0]}"
        net = -net

    flow_twh = net / 1e6
    ox, oy = label_offsets.get(line_name, (0, 0))
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

# %%
#%% Calculation of imbalance in the grid at the first timestep
t0 = network.snapshots[0]

gen_bus = network.generators_t.p.loc[t0].groupby(network.generators.bus).sum()
load_bus = network.loads_t.p.loc[t0].groupby(network.loads.bus).sum()

imbalance = gen_bus.sub(load_bus, fill_value=0)

print("Nodal imbalance at first timestep (MW):")
print(imbalance)
network.lines_t.p0.loc[t0]


#%% Plotting two pies with identical size

#%% Plotting two pies side by side with swapped order

technologies = ["wind", "solar", "biomass", "nuclear", "hydro"]

# Colors
pie_colors_map = {
    'wind': 'dodgerblue',
    'solar': 'gold',
    'biomass': 'green',
    'nuclear': 'purple',
    'hydro': 'royalblue'
}

# Create figure with 1 row, 2 columns
fig, axes = plt.subplots(1, 2, figsize=(14,7))

# -------------------
# Pie 1: Installed Capacity (now on the left)
# -------------------
pie_data_capacity = {}
for tech in technologies:
    gens = network.generators.index[network.generators.carrier == tech]
    pie_data_capacity[tech] = network.generators.p_nom_opt[gens].sum()

labels = [k for k, v in pie_data_capacity.items() if v > 0]
sizes  = [v for v in pie_data_capacity.values() if v > 0]
colors = [pie_colors_map[k] for k in labels]

axes[0].pie(
    sizes,
    radius=1,               # fixed radius
    colors=colors,
    labels=labels,
    autopct="%1.1f%%",
    wedgeprops={'linewidth':0}
)
axes[0].set_aspect('equal')
axes[0].set_title("Installed Capacity Mix")

# -------------------
# Pie 2: Dispatch (now on the right)
# -------------------
pie_data_dispatch = {}
for tech in technologies:
    gens = network.generators.index[network.generators.carrier == tech]
    pie_data_dispatch[tech] = network.generators_t.p[gens].sum().sum()

labels = [k for k, v in pie_data_dispatch.items() if v > 0]
sizes  = [v for v in pie_data_dispatch.values() if v > 0]
colors = [pie_colors_map[k] for k in labels]

axes[1].pie(
    sizes,
    radius=1,               # fixed radius
    colors=colors,
    labels=labels,
    autopct="%1.1f%%",
    wedgeprops={'linewidth':0}
)
axes[1].set_aspect('equal')
axes[1].set_title("Electricity Mix (Dispatch)")

plt.tight_layout()
plt.show()
# %%
import matplotlib.pyplot as plt
import pandas as pd

# List of technologies and regions
technologies = ["hydro", "biomass", "nuclear", "wind", "solar"]
regions = ["BRA-N", "BRA-NE", "BRA-SE", "BRA-S"]

# Colors per technology
colors_map = {
    'wind': 'dodgerblue',
    'solar': 'gold',
    'biomass': 'green',
    'nuclear': 'purple',
    'hydro': 'royalblue'
}

# ------------------------
# 1️⃣ Histogram: Optimal Capacities
# ------------------------
capacity_data = []

for region in regions:
    for tech in technologies:
        gens = network.generators.index[
            (network.generators.carrier == tech) & (network.generators.bus == f"bus {region}")
        ]
        if len(gens) > 0:
            cap = network.generators.p_nom_opt[gens].sum()
            if cap > 0:  # omit zero capacities
                capacity_data.append({"Region": region, "Technology": tech, "Capacity": cap})

df_capacity = pd.DataFrame(capacity_data)

plt.figure(figsize=(10,6))
for tech in technologies:
    df_plot = df_capacity[df_capacity["Technology"] == tech]
    plt.bar(df_plot["Region"], df_plot["Capacity"], bottom=df_capacity[df_capacity["Technology"].isin(
        [t for t in technologies if technologies.index(t) < technologies.index(tech)]
    )]["Capacity"].groupby(df_capacity["Region"]).sum().reindex(df_plot["Region"]).fillna(0), 
    color=colors_map[tech], label=tech)

plt.ylabel("Optimal Capacity (MW)")
plt.xlabel("Region")
plt.title("Optimal Installed Capacity per Region")
plt.legend(title="Technology")
plt.tight_layout()
plt.show()



# %%

technologies = ["hydro", "biomass", "nuclear", "wind", "solar"]
regions = ["BRA-N", "BRA-NE", "BRA-SE", "BRA-S"]

# Colors per technology
colors_map = {
    'wind': 'dodgerblue',
    'solar': 'gold',
    'biomass': 'green',
    'nuclear': 'purple',
    'hydro': 'royalblue'
}

# ------------------------
# Dispatch Data (sum over all time steps)
# ------------------------
dispatch_data = []
for region in regions:
    for tech in technologies:
        gens = network.generators.index[
            (network.generators.carrier == tech) & (network.generators.bus == f"bus {region}")
        ]
        if len(gens) > 0:
            # sum dispatch over all snapshots
            disp = network.generators_t.p[gens].sum().sum()
            if disp > 0:  # omit zero dispatch
                dispatch_data.append({"Region": region, "Technology": tech, "Dispatch": disp})

df_dispatch = pd.DataFrame(dispatch_data)

# ------------------------
# Regional Demand (sum over all snapshots)
# ------------------------
demand_dict = {
    "BRA-N": demand_north.sum(),
    "BRA-NE": demand_north_east.sum(),
    "BRA-SE": demand_south_east.sum(),
    "BRA-S": demand_south.sum()
}
demand_series = pd.Series(demand_dict)

# ------------------------
# Plot
# ------------------------
plt.figure(figsize=(10,6))

# Stacked bars for dispatch
bottoms = pd.Series(0, index=regions)
for tech in technologies:
    df_plot = df_dispatch[df_dispatch["Technology"] == tech].set_index("Region")
    heights = df_plot["Dispatch"].reindex(regions).fillna(0)
    plt.bar(regions, heights, bottom=bottoms, color=colors_map[tech], label=tech)
    bottoms += heights

# Overlay demand as a line with markers
plt.plot(regions, demand_series[regions], color='black', marker='o', linewidth=2, label="Total Demand")

plt.ylabel("Dispatch / Demand (MWh)")
plt.xlabel("Region")
plt.title("Regional Electricity Dispatch vs Demand")
plt.legend(title="Technology / Demand")
plt.tight_layout()
plt.show()

# %%
