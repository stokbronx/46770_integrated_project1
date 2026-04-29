#%% IMPORT
import matplotlib.pyplot as plt
from datapreparation import wind_cf_hourly, solar_cf_hourly


#%% PLOT WIND CAPACITY FACTORS
cf_july_week = wind_cf_hourly["2015-07-01":"2015-07-07"]

fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)

for ax, region in zip(axes, ["N", "NE", "SE", "S"]):
    ax.plot(cf_july_week.index, cf_july_week[region], linewidth=1.0)
    ax.set_ylabel("CF")
    ax.set_title(f"Region {region}  (yearly mean = {wind_cf_hourly[region].mean():.3f})")
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)

axes[-1].set_xlabel("Time")
fig.suptitle("Hourly Wind Capacity Factors — 1st week of July 2015", fontsize=14)
fig.tight_layout()
plt.show()


#%% PLOT SOLAR CAPACITY FACTORS
solar_july_week = solar_cf_hourly["2025-07-01":"2025-07-07"]

fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)

for ax, region in zip(axes, ["N", "NE", "SE", "S"]):
    ax.plot(solar_july_week.index, solar_july_week[region], linewidth=1.0)
    ax.set_ylabel("CF")
    ax.set_title(f"Solar {region}  (yearly mean = {solar_cf_hourly[region].mean():.3f})")
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)

axes[-1].set_xlabel("Time")
fig.suptitle("Hourly Solar Capacity Factors — 1st week of July", fontsize=14)
fig.tight_layout()
plt.show()
