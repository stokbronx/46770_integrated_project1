#%% IMPORT
import pandas as pd
pd.options.mode.string_storage = "python"
import pypsa
import matplotlib.pyplot as plt
from datapreparation import (
    wind_cf_hourly, solar_cf_hourly, demand_south_east,
)
import importlib
import parameters
importlib.reload(parameters)
from parameters import (
    capital_cost, opex_cost, marginal_cost, lifetime,
    max_capacity_hydro, annuity, annualized_cost, DISCOUNT_RATE,
)

region = 'SE'

full_2024_index = pd.date_range('2024-01-01', '2024-12-31 23:00', freq='h', tz='UTC')

wind_cf_hourly = wind_cf_hourly.copy()
if wind_cf_hourly.index.tz is None:
    wind_cf_hourly.index = wind_cf_hourly.index.tz_localize('UTC')
wind_cf_hourly = wind_cf_hourly.reindex(full_2024_index).interpolate()

solar_cf_hourly = solar_cf_hourly.copy()
if solar_cf_hourly.index.tz is None:
    solar_cf_hourly.index = solar_cf_hourly.index.tz_localize('UTC')
solar_cf_hourly = solar_cf_hourly.reindex(full_2024_index).interpolate()

demand_SE = demand_south_east.values

#%% MODEL PARAMETERS (imported from parameters.py)




#%% BUILD NETWORK
n = pypsa.Network()

#Set time frame
hours_in_2025 = pd.date_range('2024-01-01 00:00Z',
                              '2024-12-31 23:00Z',
                              freq='h')

n.set_snapshots(hours_in_2025.values)

n.add("Bus",
            "electricity bus")

n.snapshots


n.add("Load",
    "load",
    bus="electricity bus",
    p_set=demand_SE)


#%% Adding electrical technologies and carriers
# add the different carriers, only gas emits CO2
n.add("Carrier", "gas", co2_emissions=0.19) # in t_CO2/MWh_th
n.add("Carrier", "onshorewind")
n.add("Carrier", "solar")
n.add("Carrier", "biomass")
n.add("Carrier", "nuclear")
n.add("Carrier", "hydro")

# add onshore wind generator
CF_wind = wind_cf_hourly[region][[hour.strftime("%Y-%m-%dT%H:%M:%SZ") for hour in n.snapshots]]
n.add("Generator",
    "onshorewind",
    bus="electricity bus",
    p_nom_extendable=True,
    carrier="onshorewind",
    capital_cost = annualized_cost("wind"),
    marginal_cost = 0,
    p_max_pu = CF_wind.values)

# add solar PV generator
CF_solar = solar_cf_hourly[region][[hour.strftime("%Y-%m-%dT%H:%M:%SZ") for hour in n.snapshots]]

n.add("Generator",
    "solar",
    bus="electricity bus",
    p_nom_extendable=True,
    carrier="solar",
    capital_cost = annualized_cost("solar"),
    marginal_cost = 0,
    p_max_pu = CF_solar.values)

# add Biomass generator
n.add("Generator",
    "biomass",
    bus="electricity bus",
    p_nom_extendable=True,
    carrier="biomass",
    capital_cost = annualized_cost("biomass"),
    marginal_cost = marginal_cost["biomass"])

# add Nuclear generator
n.add("Generator",
    "nuclear",
    bus="electricity bus",
    p_nom_extendable=True,
    carrier="nuclear",
    capital_cost = annualized_cost("nuclear"),
    marginal_cost = marginal_cost["nuclear"])

# add hydro generator
n.add("Generator",
    "hydro",
    bus="electricity bus",
    p_nom_extendable=True,
    carrier="hydro",
    capital_cost = annualized_cost("hydro"),
    marginal_cost = marginal_cost["hydro"],
    p_nom_max=max_capacity_hydro)

n.generators_t.p_max_pu


# %% Optimize 

n.optimize(solver_name="gurobi")
#%% Print results
print(n.objective/1000000) #in 10^6 $

print(f'Cost of electricity: {n.objective/n.loads_t.p_set.sum().sum():.2f} $/MWh')
print(f'Alternative way to find cost of electricity: {n.statistics.prices()}')

n.generators.p_nom_opt # in MW

annual_generation = n.generators_t.p.sum().rename('MWh/year')
installed_capacity = n.generators.p_nom_opt.rename("MW")
tech_summary = pd.concat([installed_capacity, annual_generation], axis=1)
tech_summary = tech_summary.rename(columns={"MW": "Installed capacity [MW]", "MWh/year": "Annual generation [MWh]"})
tech_summary["Utilization [%]"] = (
    100 * tech_summary["Annual generation [MWh]"] / (tech_summary["Installed capacity [MW]"] * 8760)
).replace([float("inf"), -float("inf")], 0).fillna(0)

print("\nInstalled capacity and annual generation by technology:")
print(tech_summary.round(2).to_string())
print(f"\nTotal annual generation: {tech_summary['Annual generation [MWh]'].sum():.0f} MWh")

generators = ['hydro', 'nuclear', 'biomass', 'solar', 'onshorewind']
gen_colors = {'hydro': 'royalblue', 'nuclear': 'mediumorchid', 'biomass': 'forestgreen',
              'solar': 'gold', 'onshorewind': 'dodgerblue'}
gen_labels = {'hydro': 'Hydro', 'nuclear': 'Nuclear', 'biomass': 'Biomass',
              'solar': 'Solar', 'onshorewind': 'Onshore Wind'}

#%% LaTeX table: capacity and generation shares (requested layout)
cap = n.generators.p_nom_opt[generators]
gen = n.generators_t.p[generators].sum()
total_cap = cap.sum()
total_gen = gen.sum()

# Include only technologies with non-zero capacity or generation
table_techs = [g for g in generators if cap[g] > 0 or gen[g] > 0]

lines = []
lines.append(r"\begin{table}[h]")
lines.append(r"    \centering")
lines.append(r"    % \vspace{-10pt} % adjust if needed")
lines.append(r"    \caption{Optimal installed capacity and annual generation in SE region.}")
lines.append(r"    \label{tab:base_model_results}")
lines.append(r"    \begin{tabular}{l r r r}")
lines.append(r"        \toprule")
lines.append(r"        Technology & Capacity [\%] & Generation [\%] & Utilization [\%] \\")
lines.append(r"        \midrule")
for g in table_techs:
    c_pct = 100 * cap[g] / total_cap if total_cap > 0 else 0
    e_pct = 100 * gen[g] / total_gen if total_gen > 0 else 0
    util_pct = 100 * gen[g] / (cap[g] * 8760) if cap[g] > 0 else 0
    lines.append(f"        {gen_labels[g]:<12s} & {c_pct:4.1f} & {e_pct:4.1f} & {util_pct:4.1f} \\\\")
lines.append(r"        \midrule")
total_util_pct = 100 * total_gen / (total_cap * 8760) if total_cap > 0 else 0
lines.append(f"        Total        & {total_cap:,.0f} MW & {total_gen/1e6:,.2f} TWh & {total_util_pct:4.1f} \\\\")
lines.append(r"        \bottomrule")
lines.append(r"    \end{tabular}")
lines.append(r"    \vspace{-5pt}")
lines.append(r"\end{table}")

latex_table = "\n".join(lines)
print(latex_table)

# Summer week (Jan in southern hemisphere) and winter week (Jul)
summer_slice = slice('2024-01-08', '2024-01-14')
winter_slice = slice('2024-07-01', '2024-07-07')

dispatch_filenames = {'Summer (Jan 8–14)': 'figures/dispatch_summer.png',
                      'Winter (Jul 1–7)': 'figures/dispatch_winter.png'}

# Order stackplot from lower to higher marginal cost
# (bottom of stack first): zero-cost technologies before positive-cost.
dispatch_order = ['onshorewind', 'hydro', 'solar', 'nuclear', 'biomass']

for period_name, sl in [('Summer (Jan 8–14)', summer_slice), ('Winter (Jul 1–7)', winter_slice)]:
    fig, ax = plt.subplots(figsize=(22, 5))
    dispatch = n.generators_t.p.loc[sl, dispatch_order]
    active = [g for g in dispatch_order if dispatch[g].sum() > 0]
    ax.stackplot(dispatch.index, dispatch[active].values.T,
                 labels=[gen_labels[g] for g in active],
                 colors=[gen_colors[g] for g in active], alpha=0.85)
    ax.plot(n.loads_t.p_set.loc[sl, 'load'], color='black', linewidth=1.5, label='Demand')
    ax.set_ylim(bottom=25000)
    ax.set_ylabel('Power [MW]', fontsize=20)
    # ax.set_xlabel('Time', fontsize=20)
    ax.tick_params(axis='both', labelsize=20)
    ax.legend(loc='lower right', fontsize=14, fancybox=True, shadow=True)
    fig.autofmt_xdate()
    plt.tight_layout()
    fig.savefig(dispatch_filenames[period_name], dpi=300, bbox_inches='tight')
    plt.show()

pie_data = {g: n.generators_t.p[g].sum() for g in generators}
active_pie = [g for g in generators if pie_data[g] > 0]
pie_sizes  = [pie_data[g] for g in active_pie]
pie_cols   = [gen_colors[g] for g in active_pie]
pie_labels = [gen_labels[g] for g in active_pie]

plt.pie(pie_sizes,
        colors=pie_cols,
        labels=pie_labels,
        autopct='%1.1f%%',
        wedgeprops={'linewidth':0})
plt.axis('equal')
plt.savefig('figures/electicity_mix.png', dpi=300, bbox_inches='tight')

#%% Duration curves
import numpy as np

fig, ax = plt.subplots(figsize=(22, 5))

for gen in [g for g in generators if g != 'onshorewind']:
    sorted_dispatch = np.sort(n.generators_t.p[gen].values)[::-1]
    hours = np.arange(1, len(sorted_dispatch) + 1)
    ax.plot(hours, sorted_dispatch, color=gen_colors[gen], label=gen_labels[gen], linewidth=1.5)

demand_sorted = np.sort(n.loads_t.p_set['load'].values)[::-1]
ax.plot(np.arange(1, len(demand_sorted) + 1), demand_sorted,
        color='black', linewidth=1.5, linestyle='--', label='Demand')

ax.set_xlabel('Hours', fontsize=20)
ax.set_ylabel('Power [MW]', fontsize=20)
# ax.set_title('Duration Curves')
ax.legend(loc='lower right', fontsize=20, fancybox=True, shadow=True)
ax.tick_params(axis='both', labelsize=20)
plt.tight_layout()
fig.savefig('figures/duration_curve.png', dpi=300, bbox_inches='tight')
plt.show()

# %% 
