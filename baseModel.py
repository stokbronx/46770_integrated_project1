#%% IMPORT
import pypsa
from datapreparation import (
    demand_north, demand_south, demand_north_east, demand_south_east,
    wind_cf_hourly, solar_cf_hourly,
)


#%% MODEL PARAMETERS

# capital_cost = dict(
#     hydro=1000,
#     thermal=1000,
#     nuclear=1000,
#     wind=1000,
#     solar=1000,
# )

#MARGINAL COSTS (Needs to be updated with data from litterature)
marginal_cost = dict(
    hydro=0,
    thermal=100,
    nuclear=20,
    wind=0,
    solar=0,
)

power_plants = {
    "BRA": {"hydro": 110000, "thermal": 46500, "nuclear": 2000, "wind": 29500, "solar": 48500},
}

#Use shares from illustration in Overleaf
share = {
    "North": {"hydro": 0.1, "thermal": 0.2, "nuclear": 0.3, "wind": 0.4, "solar": 0.5},
    "South": {"hydro": 0.6, "thermal": 0.7, "nuclear": 0.8, "wind": 0.9, "solar": 1.0},
    "North-East": {"hydro": 0.1, "thermal": 0.2, "nuclear": 0.3, "wind": 0.4, "solar": 0.5},
    "South-East": {"hydro": 0.9, "thermal": 0.7, "nuclear": 0.8, "wind": 0.9, "solar": 1.0},
}

#Use demand from datapreparation.py
loads = {
    "BRA": 42000,
}


#%% BUILD NETWORK
n = pypsa.Network()

n.add("Bus", "BRA", y=-22.9, x=-43.17, v_nom=400, carrier="AC")
