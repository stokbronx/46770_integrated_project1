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
# Adding the generators to the network so that each bus has every type of generator
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
            p_nom_extendable=True, # Allow the optimization to choose the optimal capacity
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

print("Objective value:", network.objective)
print("Total system cost:", network.statistics.system_cost())
print("Total capex:", network.statistics.capex())
print("Total opex:", network.statistics.opex())
network.statistics.prices()

# %%
network.generators.p_nom_opt # Optimal capacities of the generators
# %%
network.generators_t.p # Optimal dispatch of the generators over time
#%% 
network.lines_t.p0.mean() # The active power flow on the lines can now be seen

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

#%%######## Calculation of imbalance in the grid at the first timestep####################################
t0 = network.snapshots[0]

gen_bus = network.generators_t.p.loc[t0].groupby(network.generators.bus).sum()
load_bus = network.loads_t.p.loc[t0].groupby(network.loads.bus).sum()

imbalance = gen_bus.sub(load_bus, fill_value=0)

print("Nodal imbalance at first timestep (MW):")
print(imbalance)
network.lines_t.p0.loc[t0]

# %% ################################ Visualization of regional dispatch vs demand ###############################

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
# Dispatch Data (sum over all time steps in GWh)
# ------------------------
dispatch_data = []
for region in regions:
    for tech in technologies:
        gens = network.generators.index[
            (network.generators.carrier == tech) & (network.generators.bus == f"bus {region}")
        ]
        if len(gens) > 0:
            disp = network.generators_t.p[gens].sum().sum() / 1000000  # MWh → TWh
            if disp > 0:
                dispatch_data.append({"Region": region, "Technology": tech, "Dispatch": disp})

df_dispatch = pd.DataFrame(dispatch_data)

# ------------------------
# Regional Demand (sum over all snapshots in TWh)
# ------------------------
demand_dict = {
    "BRA-N": demand_north.sum() / 1000000,
    "BRA-NE": demand_north_east.sum() / 1000000,
    "BRA-SE": demand_south_east.sum() / 1000000,
    "BRA-S": demand_south.sum() / 1000000
}
demand_series = pd.Series(demand_dict)

# ------------------------
# Plot
# ------------------------
plt.figure(figsize=(10,6))
bar_width = 0.6
bar_positions = np.arange(len(regions))

# Stacked bars for dispatch
bottoms = np.zeros(len(regions))
for tech in technologies:
    df_plot = df_dispatch[df_dispatch["Technology"] == tech].set_index("Region")
    heights = df_plot["Dispatch"].reindex(regions).fillna(0).values
    plt.bar(bar_positions, heights, bottom=bottoms, width=bar_width,
            color=colors_map[tech], label=tech, edgecolor='none')
    bottoms += heights

# Overlay dashed black edges around each bar
for i, region in enumerate(regions):
    gen = bottoms[i]
    x_left = i - bar_width/2
    x_right = i + bar_width/2
    y_bottom = 0
    y_top = gen
    # Draw dashed rectangle edges
    plt.plot([x_left, x_right], [y_bottom, y_bottom], color='black', linestyle='dashed', linewidth=1.5)  # bottom
    plt.plot([x_left, x_right], [y_top, y_top], color='black', linestyle='dashed', linewidth=1.5)        # top
    plt.plot([x_left, x_left], [y_bottom, y_top], color='black', linestyle='dashed', linewidth=1.5)      # left
    plt.plot([x_right, x_right], [y_bottom, y_top], color='black', linestyle='dashed', linewidth=1.5)    # right

# Overlay solid black line for demand and ΔE text
for i, region in enumerate(regions):
    demand = demand_series[region]
    gen = bottoms[i]
    diff = gen - demand
    # Solid demand line
    plt.hlines(y=demand, xmin=i - bar_width/2, xmax=i + bar_width/2,
               colors='black', linestyles='solid', linewidth=2)

    # ΔE label
    if region != "BRA-SE":
        text_y = gen + 0.02*max(bottoms)
        va_align = 'bottom'
    else:
        text_y = gen - 0.5*(gen - demand)
        va_align = 'center'
    plt.text(i, text_y, f"$\\Delta E={diff:.1f}$ TWh", va=va_align, ha='center', fontsize=10, color='black')

# Add a legend for the dashed edges representing generation and solid line representing demand
# We can use proxy lines for legend
from matplotlib.lines import Line2D

legend_elements = [
    Line2D([0], [0], color='black', lw=2, linestyle='solid', label='Demand'),
    Line2D([0], [0], color='black', lw=1.5, linestyle='dashed', label='Generation')
]

plt.ylabel("Dispatch / Demand (TWh)")
plt.xlabel("Region")
plt.title("Regional Electricity Dispatch vs Demand")
plt.xticks(bar_positions, regions)
plt.legend(handles=legend_elements + [plt.Rectangle((0,0),1,1,color=colors_map[tech]) for tech in technologies],
           labels=['Demand', 'Generation'] + technologies, title="Legend", bbox_to_anchor=(1.05,1))
plt.tight_layout()
plt.show()

# %% ############################# Calculation of supply shares in BRA-SE #############################
technologies = ["hydro", "biomass", "nuclear", "wind", "solar"]
region = "BRA-SE"
bus = f"bus {region}"

capacity_dict = {}
dispatch_dict = {}

# ------------------------
# Generation in BRA-SE
# ------------------------
for tech in technologies:

    gens = network.generators.index[
        (network.generators.carrier == tech) &
        (network.generators.bus == bus)
    ]

    if len(gens) > 0:
        capacity_dict[tech] = network.generators.p_nom_opt[gens].sum()
        dispatch_dict[tech] = network.generators_t.p[gens].sum().sum()
    else:
        capacity_dict[tech] = 0
        dispatch_dict[tech] = 0


# ------------------------
# Imports into BRA-SE
# ------------------------
imports = 0

for line, row in network.lines.iterrows():

    if row.bus1 == bus:
        imports += network.lines_t.p0[line].clip(lower=0).sum()

    if row.bus0 == bus:
        imports += (-network.lines_t.p0[line]).clip(lower=0).sum()

dispatch_dict["imports"] = imports


# ------------------------
# Totals
# ------------------------
total_capacity = sum(capacity_dict.values())
total_dispatch = sum(dispatch_dict.values())


print(f"\nSupply shares for {region}\n")

for tech in technologies:

    cap_share = 100 * capacity_dict[tech] / total_capacity if total_capacity > 0 else 0
    disp_share = 100 * dispatch_dict[tech] / total_dispatch if total_dispatch > 0 else 0

    if cap_share > 0 or disp_share > 0:
        print(f"{tech.capitalize():8s} | Capacity: {cap_share:6.2f}% | Dispatch: {disp_share:6.2f}%")

# Imports (dispatch only)
import_share = 100 * dispatch_dict["imports"] / total_dispatch
print(f"Imports   | Capacity:   ---  | Dispatch: {import_share:6.2f}%")
#%%############################ LCOE calculation at each bus ######################################
regions = ["BRA-N", "BRA-NE", "BRA-SE", "BRA-S"]

lcoe_results = {}

for region in regions:

    bus = f"bus {region}"

    # generators connected to this bus
    gens = network.generators.index[network.generators.bus == bus]

    # capital cost
    capex = (network.generators.p_nom_opt[gens] *
             network.generators.capital_cost[gens]).sum()

    # operational cost
    dispatch = network.generators_t.p[gens]
    marginal = network.generators.marginal_cost[gens]

    opex = (dispatch * marginal).sum().sum()

    # total generation (MWh)
    energy = dispatch.sum().sum()

    # LCOE
    if energy > 0:
        lcoe = (capex + opex) / energy
    else:
        lcoe = float("nan")

    lcoe_results[region] = lcoe


print("\nLCOE at each bus ($/MWh):")
for region, value in lcoe_results.items():
    print(f"{region}: {value:.2f} $/MWh")
