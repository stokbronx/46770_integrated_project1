#%% IMPORT
import pandas as pd
pd.options.mode.string_storage = "python"
import pypsa
import matplotlib.pyplot as plt
from datapreparation import (
    wind_cf_hourly, solar_cf_hourly, demand_south_east,
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

#%% MODEL PARAMETERS

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

lifetime = dict(
    hydro=65,
    biomass=25,
    nuclear=50,
    wind=25,
    solar=25,
)

max_capacity_hydro = 40000




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


# %% Annuity function

def annuity(n,r):
    """ Calculate the annuity factor for an asset with lifetime n years and
    discount rate  r """

    if r > 0:
        return r/(1. - 1./(1.+r)**n)
    else:
        return 1/n

#%% Adding electrical technologies and carriers
# add the different carriers, only gas emits CO2
n.add("Carrier", "gas", co2_emissions=0.19) # in t_CO2/MWh_th
n.add("Carrier", "onshorewind")
n.add("Carrier", "solar")

# add off shore wind generator
CF_wind = wind_cf_hourly[region][[hour.strftime("%Y-%m-%dT%H:%M:%SZ") for hour in n.snapshots]]
capital_cost_offshorewind = annuity(lifetime["wind"],0.07)*capital_cost["wind"]*(1+0.033) # in $/MW
n.add("Generator",
    "offshorewind",
    bus="electricity bus",
    p_nom_extendable=True,
    carrier="offshorewind",
    capital_cost = capital_cost_offshorewind,
    marginal_cost = 0,
    p_max_pu = CF_wind.values)

# add solar PV generator
CF_solar = solar_cf_hourly[region][[hour.strftime("%Y-%m-%dT%H:%M:%SZ") for hour in n.snapshots]]

capital_cost_solar = annuity(lifetime["solar"],0.07)*capital_cost["solar"]*(1+0.033) # in $/MW
n.add("Generator",
    "solar",
    bus="electricity bus",
    p_nom_extendable=True,
    carrier="solar",
    capital_cost = capital_cost_solar,
    marginal_cost = 0,
    p_max_pu = CF_solar.values)

# add Biomass generator
capital_cost_biomass = annuity(lifetime["biomass"],0.07)*capital_cost["biomass"]*(1+0.033) # in $/MW
marginal_cost_biomass = marginal_cost["biomass"] # in $/MWh_el
n.add("Generator",
    "biomass",
    bus="electricity bus",
    p_nom_extendable=True,
    carrier="biomass",
    capital_cost = capital_cost_biomass,
    marginal_cost = marginal_cost_biomass)

# add Nuclear generator
capital_cost_nuclear = annuity(lifetime["nuclear"],0.07)*capital_cost["nuclear"]*(1+0.033) # in $/MW
marginal_cost_nuclear = marginal_cost["nuclear"] # in $/MWh_el
n.add("Generator",
    "nuclear",
    bus="electricity bus",
    p_nom_extendable=True,
    carrier="nuclear",
    capital_cost = capital_cost_nuclear,
    marginal_cost = marginal_cost_nuclear)

# add hydro generator
capital_cost_hydro = annuity(lifetime["hydro"],0.07)*capital_cost["hydro"]*(1+0.033) # in $/MW
marginal_cost_hydro = marginal_cost["hydro"] # in $/MWh_el
n.add("Generator",
    "hydro",
    bus="electricity bus",
    p_nom_extendable=True,
    carrier="hydro",
    capital_cost = capital_cost_hydro,
    marginal_cost = marginal_cost_hydro,
    p_nom_max=max_capacity_hydro)

n.generators_t.p_max_pu


# %% Optimize 

n.optimize(solver_name="gurobi")
#%% Print results
print(n.objective/1000000) #in 10^6 $

print(f'Cost of electricity: {n.objective/n.loads_t.p_set.sum().sum():.2f} $/MWh')

n.generators.p_nom_opt # in MW

annual_generation = n.generators_t.p.sum().rename('MWh/year')
print("\nAnnual generation by technology (MWh):")
print(annual_generation.to_string())
print(f"\nTotal: {annual_generation.sum():.0f} MWh")

generators = ['hydro', 'nuclear', 'biomass', 'solar', 'offshorewind']
gen_colors = {'hydro': 'royalblue', 'nuclear': 'mediumorchid', 'biomass': 'forestgreen',
              'solar': 'gold', 'offshorewind': 'dodgerblue'}
gen_labels = {'hydro': 'Hydro', 'nuclear': 'Nuclear', 'biomass': 'Biomass',
              'solar': 'Solar', 'offshorewind': 'Onshore Wind'}

# Summer week (Jan in southern hemisphere) and winter week (Jul)
summer_slice = slice('2024-01-07', '2024-01-13')
winter_slice = slice('2024-07-01', '2024-07-07')

for period_name, sl in [('Summer (Jan 7–13)', summer_slice), ('Winter (Jul 1–7)', winter_slice)]:
    fig, ax = plt.subplots(figsize=(14, 5))
    dispatch = n.generators_t.p.loc[sl, generators]
    ax.stackplot(dispatch.index, dispatch.values.T,
                 labels=[gen_labels[g] for g in generators],
                 colors=[gen_colors[g] for g in generators], alpha=0.85)
    ax.plot(n.loads_t.p_set.loc[sl, 'load'], color='black', linewidth=1.5, label='Demand')
    ax.set_ylabel('Power [MW]')
    ax.set_xlabel('Time')
    ax.set_title(f'Dispatch – {period_name}')
    ax.legend(loc='upper right', fancybox=True, shadow=True)
    fig.autofmt_xdate()
    plt.tight_layout()
    plt.show()

labels = ['offshore wind',
          'solar',
          'biomass',
          'nuclear',
          'hydro']
sizes = [n.generators_t.p['offshorewind'].sum(),
         n.generators_t.p['solar'].sum(),
         n.generators_t.p['biomass'].sum(),
         n.generators_t.p['nuclear'].sum(),
         n.generators_t.p['hydro'].sum()]

colors=['blue', 'orange', 'brown', 'green', 'red']

plt.pie(sizes,
        colors=colors,
        labels=labels,
        wedgeprops={'linewidth':0})
plt.axis('equal')

plt.title('Electricity mix', y=1.07)

#%% Duration curves
import numpy as np

fig, ax = plt.subplots(figsize=(14, 5))

for gen in generators:
    sorted_dispatch = np.sort(n.generators_t.p[gen].values)[::-1]
    hours = np.arange(1, len(sorted_dispatch) + 1)
    ax.plot(hours, sorted_dispatch, color=gen_colors[gen], label=gen_labels[gen], linewidth=1.5)

demand_sorted = np.sort(n.loads_t.p_set['load'].values)[::-1]
ax.plot(np.arange(1, len(demand_sorted) + 1), demand_sorted,
        color='black', linewidth=1.5, linestyle='--', label='Demand')

ax.set_xlabel('Hours')
ax.set_ylabel('Power [MW]')
ax.set_title('Duration Curves')
ax.legend(loc='upper right', fancybox=True, shadow=True)
plt.tight_layout()
plt.show()

# %% 
