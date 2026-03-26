#%% IMPORT PACKAGES
import pandas as pd
import numpy as np
from pathlib import Path

# Data folder next to this script (works when run from any working directory)
_DATA_DIR = Path(__file__).resolve().parent / "Data"

#%% DEMAND DATA
year_to_use = 2024

df_demand_raw = pd.read_csv(_DATA_DIR / "demand_brazil.csv", parse_dates=["din_instante"])
df_demand_raw = df_demand_raw.rename(columns={
    "id_subsistema": "region",
    "din_instante": "datetime",
    "val_cargaenergiahomwmed": "demand_MW",
})
df_demand_raw = df_demand_raw.drop(columns=["nom_subsistema"])
df_demand_raw = df_demand_raw.set_index("datetime")

# Filter to the chosen year
df_demand = df_demand_raw.loc[str(year_to_use)]

demand_north      = df_demand.loc[df_demand["region"] == "N",  "demand_MW"]
demand_south      = df_demand.loc[df_demand["region"] == "S",  "demand_MW"]
demand_north_east = df_demand.loc[df_demand["region"] == "NE", "demand_MW"]
demand_south_east = df_demand.loc[df_demand["region"] == "SE", "demand_MW"]


#%% WIND CAPACITY FACTOR PROFILES — derived from power curve + wind speed data
# Power curve for a ~3.3 MW turbine (read from manufacturer data sheet).
# Wind speed data from Renewables Ninja is at 2 m height; extrapolated to hub
# height using the power-law wind profile: v(h) = v(h_ref) * (h / h_ref)^α

wind_state_to_region = {
    "BR.RJ": "SE",
    "BR.SP": "S",
    "BR.GO": "NE",
    "BR.MG": "N",
}

P_RATED = 3300  # kW

# Power curve lookup table  (wind speed [m/s] → power [kW])
pc_ws  = np.array([0,   3,   4,    5,    6,    7,     8,     9,    10,   11,   12,   13,   22,   25,  29, 30])
pc_kw  = np.array([0,   42,  180,  412,  760,  1241,  1864,  2588, 3122, 3278, 3300, 3300, 3300, 3300, 3300,   0])

HUB_HEIGHT = 100   # m

REF_HEIGHT = 2      # m  (MERRA-2 wind speed measurement height)
ALPHA      = 1/7    # Hellman exponent (neutral stability, open terrain)

df_wind = pd.read_csv(
    _DATA_DIR / "renewablesNinjaData/ninja-weather-country-BR-wind_speed_area_wtd-merra2.csv",
    skiprows=3,
    index_col="time",
    parse_dates=True,
)

df_wind = df_wind[list(wind_state_to_region.keys())]
df_wind.rename(columns=wind_state_to_region, inplace=True)

df_wind_year = df_wind.loc[f"{year_to_use}-01-01":f"{year_to_use}-12-31"]

# Extrapolate 2 m wind speeds to hub height
df_wind_hub = df_wind_year * (HUB_HEIGHT / REF_HEIGHT) ** ALPHA

# Map wind speed → power via linear interpolation of the power curve, then normalise to CF
wind_cf_hourly = df_wind_hub.apply(
    lambda col: np.interp(col, pc_ws, pc_kw) / P_RATED
)

print("Wind CF yearly averages (power-curve model):")
print(wind_cf_hourly.mean())
print("Wind hub yearly averages:")
print(df_wind_year.mean())


#%% SOLAR CAPACITY FACTOR PROFILES — simplified irradiance-only model
# Assumes constant cell temperature = 25°C (STC reference), so temperature
# correction vanishes:  CF = G / G_ref, where G_ref = 1000 W/m².
#
# Region → state mapping (same as before):
#   SE = RJ (Rio de Janeiro)
#   S  = SP (Sao Paulo)
#   NE = GO (Goias)
#   N  = MG (Minas Gerais)

G_REF = 1000  # W/m² (Standard Test Conditions reference irradiance)

irradiance_state_to_region = {
    "BR.RJ": "SE",
    "BR.SP": "S",
    "BR.GO": "NE",
    "BR.MG": "N",
}

df_irr = pd.read_csv(
    _DATA_DIR / "renewablesNinjaData/ninja-weather-country-BR-irradiance_surface_area_wtd-merra2.csv",
    skiprows=3,
    index_col="time",
    parse_dates=True,
)

df_irr = df_irr[list(irradiance_state_to_region.keys())]
df_irr.rename(columns=irradiance_state_to_region, inplace=True)

df_irr_year = df_irr.loc[f"{year_to_use}-01-01":f"{year_to_use}-12-31"]

solar_cf_hourly = (df_irr_year / G_REF).clip(upper=1.0)

print("\nSolar CF yearly averages (simplified irradiance model, T=25°C):")
print(solar_cf_hourly.mean())
