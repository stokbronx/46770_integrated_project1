#%% IMPORT
import pandas as pd
pd.options.mode.string_storage = "python"
import numpy as np
import pypsa
import matplotlib.pyplot as plt
from datapreparation import (
    solar_cf_hourly, wind_cf_hourly,
    df_irr, df_wind, df_demand_raw,
    G_REF, pc_ws, pc_kw, P_RATED,
    HUB_HEIGHT, REF_HEIGHT, ALPHA,
)

REGIONS = ["N", "NE", "SE", "S"]
YEARS = list(range(2005, 2025))
MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


#%% 20-year capacity factor statistics (2005–2024)

solar_monthly_all = {reg: pd.DataFrame(index=range(1, 13), columns=YEARS, dtype=float)
                     for reg in REGIONS}
wind_monthly_all  = {reg: pd.DataFrame(index=range(1, 13), columns=YEARS, dtype=float)
                     for reg in REGIONS}

for yr in YEARS:
    yr_slice = slice(f"{yr}-01-01", f"{yr}-12-31")

    irr_yr = df_irr.loc[yr_slice]
    solar_cf_yr = (irr_yr / G_REF).clip(upper=1.0)

    wind_yr = df_wind.loc[yr_slice]
    wind_hub_yr = wind_yr * (HUB_HEIGHT / REF_HEIGHT) ** ALPHA
    wind_cf_yr = wind_hub_yr.apply(lambda col: np.interp(col, pc_ws, pc_kw) / P_RATED)

    for reg in REGIONS:
        solar_monthly_all[reg][yr] = solar_cf_yr[reg].groupby(solar_cf_yr.index.month).mean()
        wind_monthly_all[reg][yr]  = wind_cf_yr[reg].groupby(wind_cf_yr.index.month).mean()


#%% Plot: monthly mean CF ± 1 std over 20 years — SE only

fig, axes = plt.subplots(2, 1, figsize=(6, 4.5))

s_mean = solar_monthly_all["SE"].mean(axis=1)
s_std  = solar_monthly_all["SE"].std(axis=1)
axes[0].plot(range(1, 13), s_mean, 'o-', color='goldenrod', lw=2)
axes[0].fill_between(range(1, 13), s_mean - s_std, s_mean + s_std,
                     color='gold', alpha=0.35)
axes[0].set_xticks(range(1, 13))
axes[0].set_xticklabels(MONTH_NAMES, rotation=45, fontsize=8)
axes[0].set_title('Solar — SE')
axes[0].set_ylabel('Capacity Factor')

w_mean = wind_monthly_all["SE"].mean(axis=1)
w_std  = wind_monthly_all["SE"].std(axis=1)
axes[1].plot(range(1, 13), w_mean, 's-', color='steelblue', lw=2)
axes[1].fill_between(range(1, 13), w_mean - w_std, w_mean + w_std,
                     color='lightskyblue', alpha=0.45)
axes[1].set_xticks(range(1, 13))
axes[1].set_xticklabels(MONTH_NAMES, rotation=45, fontsize=8)
axes[1].set_title('Wind — SE')
axes[1].set_ylabel('Capacity Factor')

# fig.suptitle('Monthly Capacity Factors (SE) — Mean ± 1σ  (2005–2024)', fontsize=14, y=1.01)

plt.tight_layout()
fig.savefig('figures/monthly_cf_SE.png', dpi=300, bbox_inches='tight')
plt.show()


#%% Plot: yearly capacity factor variation — SE only

solar_annual_cf = pd.Series(dtype=float, index=YEARS)
wind_annual_cf  = pd.Series(dtype=float, index=YEARS)

for yr in YEARS:
    yr_slice = slice(f"{yr}-01-01", f"{yr}-12-31")

    irr_yr = df_irr.loc[yr_slice]
    solar_annual_cf[yr] = (irr_yr["SE"] / G_REF).clip(upper=1.0).mean()

    wind_yr = df_wind.loc[yr_slice, "SE"]
    wind_hub = wind_yr * (HUB_HEIGHT / REF_HEIGHT) ** ALPHA
    wind_annual_cf[yr] = (np.interp(wind_hub, pc_ws, pc_kw) / P_RATED).mean()

fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharey=False)

axes[0].plot(YEARS, solar_annual_cf, 'o-', color='goldenrod', lw=2)
axes[0].fill_between(YEARS,
                     solar_annual_cf.mean() - solar_annual_cf.std(),
                     solar_annual_cf.mean() + solar_annual_cf.std(),
                     color='gold', alpha=0.35)
axes[0].set_title('Solar - SE')
axes[0].set_ylabel('Capacity Factor')
axes[0].set_xticks(YEARS)
axes[0].set_xticklabels(YEARS, rotation=45, fontsize=8)

axes[1].plot(YEARS, wind_annual_cf, 's-', color='steelblue', lw=2)
axes[1].fill_between(YEARS,
                     wind_annual_cf.mean() - wind_annual_cf.std(),
                     wind_annual_cf.mean() + wind_annual_cf.std(),
                     color='lightskyblue', alpha=0.45)
axes[1].set_title('Wind - SE')
axes[1].set_ylabel('Capacity Factor')
axes[1].set_xticks(YEARS)
axes[1].set_xticklabels(YEARS, rotation=45, fontsize=8)

fig.suptitle('Yearly Capacity Factor Variation — SE (2005–2024)', fontsize=14, y=1.01)
plt.tight_layout()
plt.show()


#%% Load 2024 demand data (used for all optimization runs)

region = 'SE'
demand_2024 = df_demand_raw.loc["2024"]
demand_SE = demand_2024.loc[demand_2024["region"] == region, "demand_MW"].values

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


#%% Helper: compute CFs for a given weather year from raw Renewables Ninja data

def cf_for_year(year: int):
    """Return (wind_cf, solar_cf) DataFrames with 2024 index for the given weather year."""
    yr_slice = slice(f"{year}-01-01", f"{year}-12-31")

    irr_yr = df_irr.loc[yr_slice]
    solar_cf = (irr_yr / G_REF).clip(upper=1.0)

    wind_yr = df_wind.loc[yr_slice]
    wind_hub = wind_yr * (HUB_HEIGHT / REF_HEIGHT) ** ALPHA
    wind_cf = wind_hub.apply(lambda col: np.interp(col, pc_ws, pc_kw) / P_RATED)

    for cf in (solar_cf, wind_cf):
        cf.index = cf.index.map(lambda t: t.replace(year=2024))
        if cf.index.tz is None:
            cf.index = cf.index.tz_localize('UTC')

    full_idx = pd.date_range('2024-01-01', '2024-12-31 23:00', freq='h', tz='UTC')
    solar_cf = solar_cf.reindex(full_idx).interpolate()
    wind_cf  = wind_cf.reindex(full_idx).interpolate()

    return wind_cf, solar_cf


#%% Run optimization for a given weather year

def run_model(weather_year: int, solver="gurobi"):
    """Build and optimize the network for a given weather year."""
    wind_cf, solar_cf = cf_for_year(weather_year)

    n = pypsa.Network()
    hours = pd.date_range('2024-01-01 00:00Z', '2024-12-31 23:00Z', freq='h')
    n.set_snapshots(hours.values)
    n.add("Bus", "electricity bus")

    n.add("Load", "load", bus="electricity bus", p_set=demand_SE)

    n.add("Carrier", "gas", co2_emissions=0.19)
    n.add("Carrier", "onshorewind")
    n.add("Carrier", "solar")

    CF_wind = wind_cf[region][[h.strftime("%Y-%m-%dT%H:%M:%SZ") for h in n.snapshots]]
    n.add("Generator", "onshorewind", bus="electricity bus",
          p_nom_extendable=True, carrier="onshorewind",
          capital_cost=annuity(30, 0.07) * capital_cost["wind"] * (1 + 0.033),
          marginal_cost=0, p_max_pu=CF_wind.values)

    CF_solar = solar_cf[region][[h.strftime("%Y-%m-%dT%H:%M:%SZ") for h in n.snapshots]]
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


#%% Run optimizations across all 20 weather years

results = {}
for yr in YEARS:
    print(f"\n{'='*60}")
    print(f"  Running: Weather year {yr}")
    print(f"{'='*60}")
    results[yr] = run_model(yr)


#%% Collect optimal capacities and generation across weather years

gen_names = ['hydro', 'nuclear', 'biomass', 'solar', 'onshorewind']
gen_labels_map = {'hydro': 'Hydro', 'nuclear': 'Nuclear', 'biomass': 'Biomass',
                  'solar': 'Solar', 'onshorewind': 'Onshore Wind'}
gen_colors = {'hydro': 'royalblue', 'nuclear': 'mediumorchid', 'biomass': 'forestgreen',
              'solar': 'gold', 'onshorewind': 'dodgerblue'}

cap_all = pd.DataFrame({yr: results[yr].generators.p_nom_opt[gen_names] for yr in YEARS})
cap_all.index = [gen_labels_map[g] for g in gen_names]

gen_all = pd.DataFrame({yr: results[yr].generators_t.p[gen_names].sum() for yr in YEARS})
gen_all.index = [gen_labels_map[g] for g in gen_names]

lcoe_all = pd.Series({yr: results[yr].objective / results[yr].loads_t.p_set.sum().sum()
                       for yr in YEARS})


#%% Print summary statistics

print(f"\n{'='*60}")
print("  OPTIMAL CAPACITY (MW) — Mean ± Std over 20 weather years")
print(f"{'='*60}")
cap_stats = pd.DataFrame({'Mean': cap_all.mean(axis=1), 'Std': cap_all.std(axis=1)})
print(cap_stats.round(1))

print(f"\n{'='*60}")
print("  ANNUAL GENERATION (TWh) — Mean ± Std over 20 weather years")
print(f"{'='*60}")
gen_stats = pd.DataFrame({'Mean': gen_all.mean(axis=1) / 1e6, 'Std': gen_all.std(axis=1) / 1e6})
print(gen_stats.round(2))

print(f"\n  LCOE: {lcoe_all.mean():.2f} ± {lcoe_all.std():.2f} $/MWh")


#%% Plot: optimal capacity — mean ± 1σ across weather years

fig, axes = plt.subplots(1, 2, figsize=(16, 6))

# Capacity bar chart with error bars
cap_mean = cap_all.mean(axis=1)
cap_std  = cap_all.std(axis=1)
x = np.arange(len(cap_mean))
bar_colors = [gen_colors[g] for g in gen_names]
axes[0].bar(x, cap_mean, yerr=cap_std, capsize=5,
            color=bar_colors, edgecolor='black', linewidth=0.5)
axes[0].set_xticks(x)
axes[0].set_xticklabels(cap_mean.index, rotation=0)
axes[0].set_ylabel('Installed Capacity [MW]')
axes[0].set_title('Optimal Capacity — Mean ± 1σ  (20 weather years)')

# Generation bar chart with error bars
gen_mean = gen_all.mean(axis=1) / 1e6
gen_std  = gen_all.std(axis=1) / 1e6
axes[1].bar(x, gen_mean, yerr=gen_std, capsize=5,
            color=bar_colors, edgecolor='black', linewidth=0.5)
axes[1].set_xticks(x)
axes[1].set_xticklabels(gen_mean.index, rotation=0)
axes[1].set_ylabel('Annual Generation [TWh]')
axes[1].set_title('Annual Generation — Mean ± 1σ  (20 weather years)')

plt.tight_layout()
plt.show()


#%% Plot: capacity per technology across weather years (scatter + mean line)

fig, axes = plt.subplots(1, len(gen_names), figsize=(4 * len(gen_names), 5), sharey=False)

for i, gen in enumerate(gen_names):
    ax = axes[i]
    label = gen_labels_map[gen]
    vals = cap_all.loc[label]
    ax.scatter(YEARS, vals, color=gen_colors[gen], s=30, zorder=3)
    ax.axhline(vals.mean(), color=gen_colors[gen], ls='--', lw=1.5, label=f'Mean = {vals.mean():.0f} MW')
    ax.fill_between(YEARS, vals.mean() - vals.std(), vals.mean() + vals.std(),
                    color=gen_colors[gen], alpha=0.15, label=f'± 1σ = {vals.std():.0f} MW')
    ax.set_title(label)
    ax.set_xlabel('Weather Year')
    if i == 0:
        ax.set_ylabel('Optimal Capacity [MW]')
    ax.legend(fontsize=7, loc='best')
    ax.tick_params(axis='x', rotation=45)

plt.suptitle('Optimal Capacity Sensitivity to Weather Year', fontsize=13, y=1.01)
plt.tight_layout()
plt.show()

# %%
