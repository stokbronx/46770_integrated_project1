#%% IMPORT
import pandas as pd
pd.options.mode.string_storage = "python"
import pypsa
from datapreparation import (
    demand_north, demand_south, demand_north_east, demand_south_east,
    wind_cf_hourly, solar_cf_hourly,
)

# Creation of the total demand for brazil
total_demand=demand_north+demand_south+demand_north_east+demand_south_east

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
    gas = 50,
    coal= 70,
    nuclear=20,
    wind=0,
    solar=0,
    oil=80,
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

# addition of carriers for the fuels with information on specific carbon dioxide emissions, a nice name, and colors for plotting.
n.add(
    "Carrier",
    ["coal", "gas", "oil", "hydro", "wind", "thermal", "nuclear", "solar"],
    nice_name=["Coal","Gas","Oil","Hydro","Onshore Wind","Thermal","Nuclear","Solar"
    ],
    color=["grey","indianred","black","aquamarine","dodgerblue","darkorange","purple","gold"
    ],
)
n.add("Carrier", ["electricity", "AC"])

# Addition of generators
for tech, p_nom in power_plants["BRA"].items():
    n.add(
        "Generator",
        f"BRA {tech}",
        bus="BRA",
        carrier=tech,
        p_nom=p_nom,
        marginal_cost=marginal_cost.get(tech, 0),
    )

n.generators

# Addition of loads
n.add(
    "Load",
    "BRA electricity demand",
    bus="BRA",
    p_set=loads["BRA"],
    carrier="electricity",
)


# Convert any pandas StringDtype (pyarrow) columns to plain Python objects.
# Some pandas versions use ArrowStringArray for string columns, which can cause
# issues inside PyPSA's optimization routines.
for comp in n.components:
    df = getattr(n, comp.list_name, None)
    if isinstance(df, pd.DataFrame):
        # cast any string-backed columns/index to object dtype
        for col in df.columns:
            if pd.api.types.is_string_dtype(df[col].dtype):
                df[col] = df[col].astype(object)
        if pd.api.types.is_string_dtype(df.index.dtype):
            df.index = df.index.astype(object)


# %% Optimization of the simple network
n.optimize(solver_name="highs")


# %%
