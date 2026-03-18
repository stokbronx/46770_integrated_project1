#%% IMPORT
import pandas as pd
pd.options.mode.string_storage = "python"
import numpy as np
import pypsa
import matplotlib.pyplot as plt
from datapreparation import solar_cf_hourly

#%% Wind CF generation from Portugal hourly profile + heatmap scaling

REGIONS = ["N", "NE", "SE", "S"]
TARGET_CF = {"N": 0.277384, "NE": 0.491250, "SE": 0.426221, "S": 0.425513}


def generate_wind_cf(weather_year: int) -> pd.DataFrame:
    """
    Build hourly wind capacity factors for each Brazilian region using:
      1. Portugal's hourly CF profile for the chosen weather_year
      2. Heatmap scaling factors (hour-of-day x month) per region
      3. Final scaling to match each region's long-term average CF
    """
    prt = pd.read_csv("Data/onshore_wind_1979-2017.csv", sep=";",
                       index_col="utc_time", parse_dates=True)
    prt_year = prt.loc[str(weather_year), "PRT"]

    heatmaps = {}
    for reg in REGIONS:
        hm = pd.read_csv(f"Data/heatmapData_{reg}.csv", index_col=0)
        hm.index = hm.index.astype(int)
        hm.columns = hm.columns.astype(int)
        heatmaps[reg] = hm

    result = pd.DataFrame(index=prt_year.index, columns=REGIONS, dtype=float)

    for reg in REGIONS:
        hm = heatmaps[reg]
        scaled = prt_year.copy()
        for t, cf in prt_year.items():
            scaled.at[t] = cf * hm.loc[t.hour, t.month]

        current_mean = scaled.mean()
        if current_mean > 0:
            scaled = scaled * (TARGET_CF[reg] / current_mean)

        result[reg] = scaled.values

    return result


def prepare_wind_cf_for_2024(wind_cf: pd.DataFrame) -> pd.DataFrame:
    """Remap wind CF index to 2024, reindex to full leap year, interpolate Feb 29."""
    wind_cf = wind_cf.copy()
    wind_cf.index = wind_cf.index.map(lambda t: t.replace(year=2024))
    full_idx = pd.date_range('2024-01-01', '2024-12-31 23:00', freq='h', tz='UTC')
    return wind_cf.reindex(full_idx).interpolate()


#%% Prepare baseline solar CF (from datapreparation)
solar_cf_baseline = solar_cf_hourly.copy()
solar_cf_baseline.index = solar_cf_baseline.index.map(lambda t: t.replace(year=2024))
if solar_cf_baseline.index.tz is None:
    solar_cf_baseline.index = solar_cf_baseline.index.tz_localize('UTC')
full_2024_index = pd.date_range('2024-01-01', '2024-12-31 23:00', freq='h', tz='UTC')
solar_cf_baseline = solar_cf_baseline.reindex(full_2024_index).interpolate()


#%% Generate solar CF from PS_037 inverter data

def generate_solar_cf_ps037() -> pd.DataFrame:
    """
    Build hourly solar capacity factors for the SE region from PS_037 inverter data.
    Uses actual hourly data for available months (Dec–Jun), preserving daily variability.
    Missing months (Jul–Nov) are filled by mirroring around the winter solstice (Jun 21),
    using averaged diurnal profiles only for those months.
    """
    RATED_CAPACITY_W = 2_000_000  # ~2 MW peak from 8 inverters

    df = pd.read_csv("Data/PS_037.csv", parse_dates=["datetime"])
    plant_power = df.groupby("datetime")["total_active_power_w"].sum()
    plant_power.index = pd.to_datetime(plant_power.index, utc=True)

    hourly_power = plant_power.resample("h").mean()
    hourly_cf = (hourly_power / RATED_CAPACITY_W).clip(0, 1).fillna(0)

    # Remap actual data to 2024: Dec 2024 stays Dec 2024, Jan–Jun 2025 → Jan–Jun 2024
    hourly_cf_2024 = hourly_cf.copy()
    hourly_cf_2024.index = hourly_cf_2024.index.map(lambda t: t.replace(year=2024))

    full_idx = pd.date_range('2024-01-01', '2024-12-31 23:00', freq='h', tz='UTC')
    cf_series = hourly_cf_2024.reindex(full_idx)

    # Build averaged diurnal profiles for mirroring missing months (Jul–Nov)
    profiles = hourly_cf.to_frame("cf")
    profiles["month"] = profiles.index.month
    profiles["hour"] = profiles.index.hour
    diurnal = profiles.groupby(["month", "hour"])["cf"].mean()

    mirror_map = {7: 6, 8: 5, 9: 4, 10: 3, 11: 2}
    for missing_month, source_month in mirror_map.items():
        if source_month in diurnal.index.get_level_values(0):
            diurnal = pd.concat([diurnal, diurnal.loc[source_month].rename(
                lambda h: (missing_month, h))])

    # Fill only the NaN gaps (Jul–Nov) with mirrored average profiles
    for t in full_idx:
        if pd.isna(cf_series[t]):
            try:
                cf_series[t] = diurnal.loc[(t.month, t.hour)]
            except KeyError:
                cf_series[t] = 0.0

    # # Scale to match the same annual mean CF as the baseline SE profile
    # baseline_mean = solar_cf_baseline["SE"].mean()
    # ps037_mean = cf_series.mean()
    # if ps037_mean > 0:
    #     cf_series = cf_series * (baseline_mean / ps037_mean)

    # Create a full DataFrame with all regions (use baseline for N, NE, S)
    result = solar_cf_baseline.copy()
    result["SE"] = cf_series.values

    return result


solar_cf_ps037 = generate_solar_cf_ps037()

print("Solar CF monthly means – SE region:")
print("  Baseline vs PS_037:")
comparison = pd.DataFrame({
    "Baseline": solar_cf_baseline["SE"].resample("MS").mean(),
    "PS_037":   solar_cf_ps037["SE"].resample("MS").mean(),
})
print(comparison.round(4))


#%% Load demand data
df_elec = pd.read_csv('data/demand_processed.csv', sep=',', index_col="din_instante")
df_elec.index = pd.to_datetime(df_elec.index)
region = 'SE'
df_elec_SE = df_elec.loc[df_elec["region"] == region].drop(columns=["region"])

#%% Model parameters
capital_cost = dict(
    hydro=3750000,
    biomass=3750000,
    nuclear=7500000,
    wind=2100000,
    solar=1250000,
)

marginal_cost = dict(
    hydro=5,
    biomass=75,
    nuclear=12,
    wind=0,
    solar=0,
)

max_capacity_hydro = 40000


def annuity(n, r):
    if r > 0:
        return r / (1.0 - 1.0 / (1.0 + r) ** n)
    else:
        return 1 / n


#%% Run optimization for a given scenario

def run_model(weather_year: int, solar_data: pd.DataFrame, solver="gurobi"):
    """Build and optimize the network for a given wind weather year and solar CF profile."""
    wind_cf_raw = generate_wind_cf(weather_year)
    wind_cf = prepare_wind_cf_for_2024(wind_cf_raw)

    n = pypsa.Network()
    hours = pd.date_range('2024-01-01 00:00Z', '2024-12-31 23:00Z', freq='h')
    n.set_snapshots(hours.values)
    n.add("Bus", "electricity bus")

    n.add("Load", "load", bus="electricity bus",
          p_set=df_elec_SE["demand [MW]"].values)

    n.add("Carrier", "gas", co2_emissions=0.19)
    n.add("Carrier", "onshorewind")
    n.add("Carrier", "solar")

    CF_wind = wind_cf[region][[h.strftime("%Y-%m-%dT%H:%M:%SZ") for h in n.snapshots]]
    n.add("Generator", "onshorewind", bus="electricity bus",
          p_nom_extendable=True, carrier="onshorewind",
          capital_cost=annuity(30, 0.07) * capital_cost["wind"] * (1 + 0.033),
          marginal_cost=0, p_max_pu=CF_wind.values)

    CF_solar = solar_data[region][[h.strftime("%Y-%m-%dT%H:%M:%SZ") for h in n.snapshots]]
    n.add("Generator", "solar", bus="electricity bus",
          p_nom_extendable=True, carrier="solar",
          capital_cost=annuity(25, 0.07) * capital_cost["solar"] * (1 + 0.033),
          marginal_cost=0, p_max_pu=CF_solar.values)

    n.add("Generator", "biomass", bus="electricity bus",
          p_nom_extendable=True, carrier="biomass",
          capital_cost=annuity(25, 0.07) * capital_cost["biomass"] * (1 + 0.033),
          marginal_cost=marginal_cost["biomass"])

    n.add("Generator", "nuclear", bus="electricity bus",
          p_nom_extendable=True, carrier="nuclear",
          capital_cost=annuity(60, 0.07) * capital_cost["nuclear"] * (1 + 0.033),
          marginal_cost=marginal_cost["nuclear"])

    n.add("Generator", "hydro", bus="electricity bus",
          p_nom_extendable=True, carrier="hydro",
          capital_cost=annuity(60, 0.07) * capital_cost["hydro"] * (1 + 0.033),
          marginal_cost=marginal_cost["hydro"],
          p_nom_max=max_capacity_hydro)

    n.optimize(solver_name=solver)
    return n


#%% Define scenarios: (label, wind_year, solar_data)
scenarios = {
    "2015 wind + baseline solar": (2015, solar_cf_baseline),
    "2014 wind + baseline solar": (2014, solar_cf_baseline),
    "2015 wind + PS_037 solar":   (2015, solar_cf_ps037),
    "2014 wind + PS_037 solar":   (2014, solar_cf_ps037),
}

results = {}
for label, (wind_yr, solar_data) in scenarios.items():
    print(f"\n{'='*60}")
    print(f"  Running: {label}")
    print(f"{'='*60}")
    results[label] = run_model(wind_yr, solar_data)


#%% Compare results

gen_names = ['hydro', 'nuclear', 'biomass', 'solar', 'onshorewind']
gen_labels_map = {'hydro': 'Hydro', 'nuclear': 'Nuclear', 'biomass': 'Biomass',
                  'solar': 'Solar', 'onshorewind': 'Onshore Wind'}
gen_colors = {'hydro': 'royalblue', 'nuclear': 'mediumorchid', 'biomass': 'forestgreen',
              'solar': 'gold', 'onshorewind': 'dodgerblue'}

# Optimal capacities
print(f"\n{'='*60}")
print("  OPTIMAL INSTALLED CAPACITIES (MW)")
print(f"{'='*60}")
cap_df = pd.DataFrame({label: results[label].generators.p_nom_opt for label in scenarios})
cap_df.index = [gen_labels_map.get(g, g) for g in cap_df.index]
print(cap_df.round(1))

# Annual generation
print(f"\n{'='*60}")
print("  ANNUAL GENERATION (MWh)")
print(f"{'='*60}")
gen_df = pd.DataFrame({label: results[label].generators_t.p.sum() for label in scenarios})
gen_df.index = [gen_labels_map.get(g, g) for g in gen_df.index]
print(gen_df.round(0))

# System cost
print(f"\n{'='*60}")
print("  SYSTEM COST")
print(f"{'='*60}")
for label in scenarios:
    n = results[label]
    total_load = n.loads_t.p_set.sum().sum()
    print(f"  {label}: Total = {n.objective/1e6:.1f} M$, "
          f"LCOE = {n.objective/total_load:.2f} $/MWh")


#%% Bar chart comparison
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

cap_compare = pd.DataFrame({
    label: results[label].generators.p_nom_opt[gen_names] for label in scenarios
})
cap_compare.index = [gen_labels_map[g] for g in gen_names]
cap_compare.plot.bar(ax=axes[0], rot=0)
axes[0].set_ylabel('Installed Capacity [MW]')
axes[0].set_title('Optimal Capacity by Scenario')
axes[0].legend(fontsize=7, title='Scenario')

gen_compare = pd.DataFrame({
    label: results[label].generators_t.p[gen_names].sum() / 1e6 for label in scenarios
})
gen_compare.index = [gen_labels_map[g] for g in gen_names]
gen_compare.plot.bar(ax=axes[1], rot=0)
axes[1].set_ylabel('Annual Generation [TWh]')
axes[1].set_title('Annual Generation by Scenario')
axes[1].legend(fontsize=7, title='Scenario')

plt.tight_layout()
plt.show()


#%% Dispatch comparison – summer and winter weeks (baseline solar vs PS_037, both using 2015 wind)
summer_slice = slice('2024-01-07', '2024-01-13')
winter_slice = slice('2024-07-01', '2024-07-07')

compare_labels = ["2015 wind + baseline solar", "2015 wind + PS_037 solar"]

for period_name, sl in [('Summer (Jan 7–13)', summer_slice), ('Winter (Jul 1–7)', winter_slice)]:
    fig, axes = plt.subplots(1, 2, figsize=(16, 5), sharey=True)
    for ax, label in zip(axes, compare_labels):
        n = results[label]
        dispatch = n.generators_t.p.loc[sl, gen_names]
        ax.stackplot(dispatch.index, dispatch.values.T,
                     labels=[gen_labels_map[g] for g in gen_names],
                     colors=[gen_colors[g] for g in gen_names], alpha=0.85)
        ax.plot(n.loads_t.p_set.loc[sl, 'load'], color='black', lw=1.5, label='Demand')
        ax.set_ylabel('Power [MW]')
        ax.set_title(f'{period_name}\n{label}')
        ax.legend(loc='upper right', fontsize=7)
    fig.autofmt_xdate()
    plt.tight_layout()
    plt.show()

# %%
