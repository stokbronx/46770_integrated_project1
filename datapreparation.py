#%% IMPORT PACKAGES
import pandas as pd
import numpy as np
from pathlib import Path

# Data folder next to this script (works when run from any working directory)
_DATA_DIR = Path(__file__).resolve().parent / "Data"

#%% DEMAND DATA
df_demand = pd.read_csv(_DATA_DIR / "demand_processed.csv", index_col=0, parse_dates=True)

demand_north = df_demand.loc[df_demand["region"] == "N"]
demand_south = df_demand.loc[df_demand["region"] == "S"]
demand_north_east = df_demand.loc[df_demand["region"] == "NE"]
demand_south_east = df_demand.loc[df_demand["region"] == "SE"]


#%% WIND CAPACITY FACTOR PROFILES
wind_cf_hourly = pd.read_csv(_DATA_DIR / "wind_cf_hourly.csv", index_col=0, parse_dates=True)

print("Wind CF yearly averages (verification):")
print(wind_cf_hourly.mean())


#%% SOLAR CAPACITY FACTOR PROFILES
# SE = RJ (Rio de Janeiro)  PS_002
# S  = SP (Sao Paulo)       PS_001
# NE = GO (Goias)           PS_005  (no full-year BA data available)
# N  = MG (Minas Gerais)    PS_006  (no full-year N data available)
solar_cf_hourly = pd.read_csv(_DATA_DIR / "solar_cf_hourly.csv", index_col=0, parse_dates=True)

print("\nSolar CF yearly averages:")
print(solar_cf_hourly.mean())
