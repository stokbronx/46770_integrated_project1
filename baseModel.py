#%% IMPORT
import pandas as pd
pd.options.mode.string_storage = "python"
import pypsa
from pathlib import Path
import matplotlib.pyplot as plt
from datapreparation import (
    demand_north, demand_south, demand_north_east, demand_south_east,
    wind_cf_hourly, solar_cf_hourly,
)

wind_cf_hourly.index = wind_cf_hourly.index.map(lambda t: t.replace(year=2024))
full_2024_index = pd.date_range('2024-01-01', '2024-12-31 23:00', freq='h', tz='UTC')
wind_cf_hourly = wind_cf_hourly.reindex(full_2024_index).interpolate()

solar_cf_hourly.index = solar_cf_hourly.index.map(lambda t: t.replace(year=2024))
if solar_cf_hourly.index.tz is None:
    solar_cf_hourly.index = solar_cf_hourly.index.tz_localize('UTC')
solar_cf_hourly = solar_cf_hourly.reindex(full_2024_index).interpolate()

# Creation of the total demand for brazil
total_demand=demand_north+demand_south+demand_north_east+demand_south_east

#%% MODEL PARAMETERS

capital_cost = dict(
    hydro=3750000, # $/MW
    #gas=1000,
    #coal=1000,
    biomass=3750000, # $/MW
    nuclear=7500000, # $/MW
    wind=2100000, # $/MW
    solar=1250000, # $/MW
)

#JOINT CAPACITY AND DISPATCH OPTIMIZATION (NOMINAL CAPACITY IS A DECISION VARIABLE, NOT FIXED)

#MARGINAL COSTS (Needs to be updated with data from litterature)
marginal_cost = dict(
    hydro=5, # $/MWh
    #gas=1000,
    #coal=100,
    biomass=75, # $/MWh
    nuclear=12, # $/MWh 
    wind=0, # $/MWh
    solar=0, # $/MWh
)



# # Regional shares estimated from the power plant map (each tech sums to 1.0 across regions)
# share = {
#     "North":      {"hydro": 0.30, "thermal": 0.10, "nuclear": 0.00, "wind": 0.02, "solar": 0.05},
#     "South":      {"hydro": 0.20, "thermal": 0.15, "nuclear": 0.00, "wind": 0.08, "solar": 0.05},
#     "North-East": {"hydro": 0.10, "thermal": 0.30, "nuclear": 0.00, "wind": 0.85, "solar": 0.60},
#     "South-East": {"hydro": 0.40, "thermal": 0.45, "nuclear": 1.00, "wind": 0.05, "solar": 0.30},
# }

# bra_capacity = {"hydro": 110000, "thermal": 46500, "nuclear": 2000, "wind": 29500, "solar": 48500}

# power_plants = {"BRA": bra_capacity}
# for region in share:
#     power_plants[region] = {tech: bra_capacity[tech] * share[region][tech] for tech in bra_capacity}

#Use demand from datapreparation.py
# load electricity demand data (path relative to this script)
_DATA_DIR = Path(__file__).resolve().parent / "Data"
df_elec = pd.read_csv(_DATA_DIR / "demand_processed.csv", sep=',', index_col="din_instante") # in MWh
df_elec.index = pd.to_datetime(df_elec.index) #change index to datatime
region='SE'
df_elec_SE = df_elec.loc[df_elec["region"]==region]
df_elec_SE.drop(columns=["region"], inplace=True)
print(df_elec_SE.head())


#%% Max capacities for hydro

max_capacity_hydro = 40000 #GW




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


# add load to the bus
n.add("Load",
    "load",
    bus="electricity bus",
    p_set=df_elec_SE["demand [MW]"].values)

n.loads_t.p_set


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
capital_cost_offshorewind = annuity(30,0.07)*capital_cost["wind"]*(1+0.033) # in $/MW
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
capital_cost_solar = annuity(25,0.07)*capital_cost["solar"]*(1+0.033) # in $/MW
n.add("Generator",
    "solar",
    bus="electricity bus",
    p_nom_extendable=True,
    carrier="solar",
    capital_cost = capital_cost_solar,
    marginal_cost = 0,
    p_max_pu = CF_solar.values)

# add Biomass generator
capital_cost_biomass = annuity(25,0.07)*capital_cost["biomass"]*(1+0.033) # in $/MW
marginal_cost_biomass = marginal_cost["biomass"] # in $/MWh_el
n.add("Generator",
    "biomass",
    bus="electricity bus",
    p_nom_extendable=True,
    carrier="biomass",
    capital_cost = capital_cost_biomass,
    marginal_cost = marginal_cost_biomass)

# add Nuclear generator
capital_cost_nuclear = annuity(60,0.07)*capital_cost["nuclear"]*(1+0.033) # in $/MW
marginal_cost_nuclear = marginal_cost["nuclear"] # in $/MWh_el
n.add("Generator",
    "nuclear",
    bus="electricity bus",
    p_nom_extendable=True,
    carrier="nuclear",
    capital_cost = capital_cost_nuclear,
    marginal_cost = marginal_cost_nuclear)

# add hydro generator
capital_cost_hydro = annuity(60,0.07)*capital_cost["hydro"]*(1+0.033) # in $/MW
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

# %% 
