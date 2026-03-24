#%% # loading of data and libraries
import pandas as pd
#pd.options.mode.string_storage = "python"

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
network.add("Line"," line S-NE", bus0 = "bus BRA-S", bus1= "bus BRA-NE", x=0.1, r=0.01, carrier="AC",s_nom=1100)
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
network.lines_t.p0 # The active power flow on the lines can now be seen

# %% ###########################3 Plotting of the network ############################

fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"projection": ccrs.PlateCarree()})
ax.set_extent([-75, -30, -35, 7], crs=ccrs.PlateCarree())
ax.add_feature(cfeature.LAND, facecolor="whitesmoke")
ax.add_feature(cfeature.OCEAN, facecolor="lightcyan")
ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
ax.add_feature(cfeature.BORDERS, linewidth=0.5, linestyle="--")
ax.add_feature(cfeature.STATES, linewidth=0.3, edgecolor="gray")

network.plot(ax=ax, bus_sizes=0.1, line_widths=2, margin=0.2,
             bus_colors="red", line_colors="steelblue",
             title="Brazilian Power Network")
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


# %%
