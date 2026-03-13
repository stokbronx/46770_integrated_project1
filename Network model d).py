#%% # loading of data and libraries
import pandas as pd
pd.options.mode.string_storage = "python"
import pypsa
from datapreparation import (
    demand_north, demand_south, demand_north_east, demand_south_east,
    wind_cf_hourly, solar_cf_hourly,)

#%% Adding the buses to the network
network = pypsa.Network()
network.add("Bus", "bus BRA-N", v_nom=400000.0)
network.add("Bus", "bus BRA-NE", v_nom=400000.0)
network.add("Bus", "bus BRA-S", v_nom=400000.0)
network.add("Bus", "bus BRA-SE", v_nom=400000.0)
network.buses

# Adding the network lines between the buses
network.add("Line"," line N-NE", bus0 = "bus BRA-N", bus1= "bus BRA-NE", x=0.1, r=0.01)
network.add("Line"," line NE-SE", bus0 = "bus BRA-NE", bus1= "bus BRA-SE", x=0.1, r=0.01)
network.add("Line"," line SE-S", bus0 = "bus BRA-SE", bus1= "bus BRA-S", x=0.1, r=0.01)
network.add("Line"," line SE-N", bus0 = "bus BRA-SE", bus1= "bus BRA-N", x=0.1, r=0.01)
network.add("Line"," line S-NE", bus0 = "bus BRA-S", bus1= "bus BRA-NE", x=0.1, r=0.01)


network.lines
# %% Adding the generators to the network
power_plants = { 
    "BRA": {"hydro": 110000, "thermal": 46500, "nuclear": 2000, "wind": 29500, "solar": 48500},
} #####These capacities needs to be changed when the optimal values are found############

share = { #####These shares needs to be changed when the optimal values are found############
    "BRA-N": {"hydro": 0.1, "thermal": 0.2, "nuclear": 0.3, "wind": 0.4, "solar": 0.5},
    "BRA-S": {"hydro": 0.6, "thermal": 0.7, "nuclear": 0.8, "wind": 0.9, "solar": 1.0},
    "BRA-NE": {"hydro": 0.1, "thermal": 0.2, "nuclear": 0.3, "wind": 0.4, "solar": 0.5},
    "BRA-SE": {"hydro": 0.9, "thermal": 0.7, "nuclear": 0.8, "wind": 0.9, "solar": 1.0},
}
# Compute regional capacities
regional_capacities = {}

for region, tech_shares in share.items():
    regional_capacities[region] = {}
    for tech, total_capacity in power_plants["BRA"].items():
        regional_capacities[region][tech] = total_capacity * tech_shares[tech]

# Marginal costs (example values)
marginal_costs = {
    "hydro": 5,
    "thermal": 50,
    "nuclear": 10,
    "wind": 0,
    "solar": 0,
}

# Add generators to the network
for region, techs in regional_capacities.items():
    for tech, capacity in techs.items():
        network.add(
            "Generator",
            f"{tech} {region}",
            bus=f"bus {region}",
            p_nom=capacity,
            marginal_cost=marginal_costs[tech]
        )
network.generators
# %% Now the loads are added to the network

from datapreparation import (
    demand_north, demand_south, demand_north_east, demand_south_east,
    wind_cf_hourly, solar_cf_hourly,
)
demand_north = demand_north.loc[demand_north["region"] == "N"]["demand [MW]"]
demand_south = demand_south.loc[demand_south["region"] == "S"]["demand [MW]"]
demand_north_east = demand_north_east.loc[demand_north_east["region"] == "NE"]["demand [MW]"]
demand_south_east = demand_south_east.loc[demand_south_east["region"] == "SE"]["demand [MW]"]


demand = {
    "BRA-N": demand_north,
    "BRA-S": demand_south,
    "BRA-NE": demand_north_east,
    "BRA-SE": demand_south_east,
}

for region, demand_ts in demand.items():

    # Ensure Series and align with snapshots
    demand_ts = demand_ts.reindex(network.snapshots)

    network.add(
        "Load",
        f"load {region}",
        bus=f"bus {region}",
        p_set=demand_ts
    )

demand_ts = demand_ts.reindex(network.snapshots)



# %%
