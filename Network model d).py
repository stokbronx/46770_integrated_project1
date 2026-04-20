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
import importlib
import parameters
importlib.reload(parameters)
from parameters import (
    capital_cost, opex_cost, marginal_cost, lifetime,
    max_capacity_hydro, annuity, annualized_cost, DISCOUNT_RATE,
)

#%% Adding the buses to the network
network = pypsa.Network()

network.add(
    "Carrier",
    ["hydro", "biomass", "nuclear", "wind", "solar", "battery"],
    nice_name=["Hydro", "Biomass", "Nuclear", "Wind", "Solar", "Battery"],
    color=["aquamarine", "sienna", "purple", "dodgerblue", "gold", "violet"]
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

region_cf_map = {"BRA-N":"N","BRA-S":"S","BRA-NE":"NE","BRA-SE":"SE"}
regions = ["BRA-N","BRA-NE","BRA-SE","BRA-S"]
technologies = ["hydro","biomass","nuclear","wind","solar"]

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

# Generation per bus
gen_bus = network.generators_t.p.loc[t0].groupby(network.generators.bus).sum()

# Load per bus
load_bus = network.loads_t.p.loc[t0].groupby(network.loads.bus).sum()

# 🔋 Storage per bus (IMPORTANT)
# positive = discharge (supply), negative = charging (demand)
storage_bus = network.storage_units_t.p.loc[t0].groupby(network.storage_units.bus).sum()

# Replace NaNs with 0 to align indices
gen_bus = gen_bus.reindex(network.buses.index).fillna(0)
load_bus = load_bus.reindex(network.buses.index).fillna(0)
storage_bus = storage_bus.reindex(network.buses.index).fillna(0)

# ✅ Correct nodal balance (excluding flows for now)
imbalance = gen_bus + storage_bus - load_bus

print("Nodal balance WITHOUT flows (MW):")
print(imbalance)

# Line flows
print("\nLine flows (MW):")
print(network.lines_t.p0.loc[t0])

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
    if region in regions:
        text_y = gen + 0.02*max(bottoms)
        va_align = 'bottom'
    
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
plt.ylim(0,450)
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


import_share = 100 * dispatch_dict["imports"] / total_dispatch
print(f"Imports   | Capacity:   ---  | Dispatch: {import_share:6.2f}%")

# BATTERY CONTRIBUTION (SEPARATE METRICS)
# ------------------------

battery_units = network.storage_units.index[
    network.storage_units.bus == bus
]

# Installed battery power (MW)
battery_power = network.storage_units.p_nom_opt[battery_units].sum()

# Energy capacity (MWh)
battery_energy = (
    battery_power *
    network.storage_units.loc[battery_units, "max_hours"].iloc[0]
)

# ------------------------
# Battery dispatch (IMPORTANT: split charge/discharge)
# ------------------------

battery_dispatch = network.storage_units_t.p[battery_units]

# Discharging = positive contribution to system supply
battery_discharge = battery_dispatch.clip(lower=0).sum().sum()

# Total system generation + storage discharge (same denominator style as your model)
total_system_dispatch = (
    network.generators_t.p.sum().sum()
)

# ------------------------
# PERCENTAGES
# ------------------------

battery_power_share = (
    100 * battery_power / (network.generators.p_nom_opt.sum() + battery_power)
)

battery_dispatch_share = (
    100 * battery_discharge / (total_system_dispatch + battery_discharge)
)
# ------------------------
# BATTERY CAPACITY SHARE (MW BASIS)
# ------------------------

# Total generator capacity (MW)
total_generator_capacity = network.generators.p_nom_opt.sum()

# Battery capacity (MW)
battery_capacity_mw = battery_power  # already computed earlier

# System total capacity including battery
total_system_capacity = total_generator_capacity + battery_capacity_mw

# Battery capacity share
battery_capacity_share = (
    100 * battery_capacity_mw / total_system_capacity
    if total_system_capacity > 0 else 0
)

print(f"\nBattery contribution in {region}\n")
print(f"Battery capacity share: {battery_capacity_share:.2f}% of total system capacity")
print(f"Dispatch share:        {battery_dispatch_share:.2f}% of total generation")

#%%############################ LCOE calculation at each bus ######################################
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
