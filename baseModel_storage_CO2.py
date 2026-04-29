#%% IMPORT
from __future__ import annotations

import pandas as pd
pd.options.mode.string_storage = "python"
import pypsa
import logging
from pathlib import Path
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

# Silence verbose optimization/logger output from PyPSA/Linopy backends.
logging.getLogger("pypsa").setLevel(logging.ERROR)
logging.getLogger("linopy").setLevel(logging.ERROR)
logging.getLogger("gurobipy").setLevel(logging.ERROR)
logging.getLogger("highspy").setLevel(logging.ERROR)

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
#n.add("Carrier", "gas", co2_emissions=0.19) # in t_CO2/MWh_th
n.add("Carrier", "onshorewind", co2_emissions=0.0)
n.add("Carrier", "solar", co2_emissions=0.0)
n.add("Carrier", "biomass", co2_emissions=0.210)
n.add("Carrier", "nuclear", co2_emissions=0.0)
n.add("Carrier", "hydro", co2_emissions=0.0)

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
    marginal_cost = marginal_cost["biomass"],
    efficiency = 0.35)

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


# %% Optimize (baseline — no storage)
# Keep an unfixed copy so we can run part (C) as a joint re-optimization with storage.
n_before_opt = n.copy()

n.optimize(solver_name="gurobi", log_to_console=False, solver_options={"OutputFlag": 0})
#%% Print results
print(n.objective/1000000) #in 10^6 $

print(f'Cost of electricity: {n.objective/n.loads_t.p_set.sum().sum():.2f} $/MWh')

n.generators.p_nom_opt # in MW

annual_generation = n.generators_t.p.sum().rename('MWh/year')
print("\nAnnual generation by technology (MWh):")
print(annual_generation.to_string())
print(f"\nTotal: {annual_generation.sum():.0f} MWh")

generators = ['hydro', 'nuclear', 'biomass', 'solar', 'onshorewind']
gen_colors = {'hydro': 'royalblue', 'nuclear': 'mediumorchid', 'biomass': 'forestgreen',
              'solar': 'gold', 'onshorewind': 'dodgerblue'}
gen_labels = {'hydro': 'Hydro', 'nuclear': 'Nuclear', 'biomass': 'Biomass',
              'solar': 'Solar', 'onshorewind': 'Onshore Wind'}

# Summer week (Jan in southern hemisphere) and winter week (Jul)
summer_slice = slice('2024-01-07', '2024-01-13')
winter_slice = slice('2024-07-01', '2024-07-07')

dispatch_filenames = {'Summer (Jan 7–13)': 'figures/dispatch_summer.png',
                      'Winter (Jul 1–7)': 'figures/dispatch_winter.png'}

for period_name, sl in [('Summer (Jan 7–13)', summer_slice), ('Winter (Jul 1–7)', winter_slice)]:
    fig, ax = plt.subplots(figsize=(14, 5))
    dispatch = n.generators_t.p.loc[sl, generators]
    active = [g for g in generators if dispatch[g].sum() > 0]
    ax.stackplot(dispatch.index, dispatch[active].values.T,
                 labels=[gen_labels[g] for g in active],
                 colors=[gen_colors[g] for g in active], alpha=0.85)
    ax.plot(n.loads_t.p_set.loc[sl, 'load'], color='black', linewidth=1.5, label='Demand')
    ax.set_ylabel('Power [MW]')
    ax.set_xlabel('Time')
    ax.set_title(f'Dispatch – {period_name}')
    ax.legend(loc='upper right', fancybox=True, shadow=True)
    fig.autofmt_xdate()
    plt.tight_layout()
    fig.savefig(dispatch_filenames[period_name], dpi=300, bbox_inches='tight')
    plt.show()

pie_data = {
    'onshore wind': n.generators_t.p['onshorewind'].sum(),
    'solar':        n.generators_t.p['solar'].sum(),
    'biomass':      n.generators_t.p['biomass'].sum(),
    'nuclear':      n.generators_t.p['nuclear'].sum(),
    'hydro':        n.generators_t.p['hydro'].sum(),
}
pie_colors_map = {
    'onshore wind': 'blue', 'solar': 'orange', 'biomass': 'brown',
    'nuclear': 'green', 'hydro': 'red',
}

labels = [k for k, v in pie_data.items() if v > 0]
sizes  = [v for v in pie_data.values() if v > 0]
colors = [pie_colors_map[k] for k in labels]

plt.pie(sizes,
        colors=colors,
        labels=labels,
        autopct=lambda p: f"{p:.1f}%" if p >= 1 else "",
        wedgeprops={'linewidth':0})
plt.axis('equal')

plt.title('Electricity mix', y=1.07)
plt.savefig('figures/electicity_mix.png', dpi=300, bbox_inches='tight')

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
fig.savefig('figures/duration_curve.png', dpi=300, bbox_inches='tight')
plt.show()

# %% 


########################## storage model (part C) ##########################
# Joint capacity + dispatch with battery (BESS) + hydrogen (electrolyzer, H2 store, fuel cell).
# Uses the same snapshots/load/renewables as the baseline build via `n_before_opt`.
# All plotting/helpers below are confined to part (C); figures saved under figures/partC_*.png

def _savefig_close_partc(fig, path: str) -> None:
    """Save Part (C) figure and close — no plt.show() so the script does not block on C plots."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)

# Battery capex (part C only): split power and energy to make duration endogenous.
# Chosen so a 4h battery has total capex close to 450 $/kW:
# 150,000 $/MW (power) + 4 * 75,000 $/MWh (energy) = 450,000 $/MW
battery_power_capex_per_MW = 150_000.0   # $/MW converter/power block
battery_energy_capex_per_MWh = 75_000.0  # $/MWh energy block

# --- Economic / technical assumptions (aligned with report + course examples) ---
OM_FRAC = 0.033

battery_lifetime_years = 15
battery_eff_store = 0.95
battery_eff_dispatch = 0.95

# Hydrogen chain (typical PyPSA-style parameters)
h2_electrolyzer_eff = 0.70  # H2 energy equivalent per electricity in
h2_fuelcell_eff = 0.55  # electricity out per H2 in
h2_electrolyzer_capex_overnight = 700_000.0  # $/MW
h2_fuelcell_capex_overnight = 800_000.0  # $/MW
h2_storage_capex_overnight = 10_000.0  # $/MWh
h2_chain_lifetime_years = 30


def _annuity_overnight_to_annualized(overnight_per_mw_or_mwh, lifetime_years):
    """Match generator cost style: annuity * overnight * (1 + OM)."""
    return annuity(lifetime_years, DISCOUNT_RATE) * overnight_per_mw_or_mwh * (1 + OM_FRAC)


battery_power_capital_cost = _annuity_overnight_to_annualized(
    battery_power_capex_per_MW, battery_lifetime_years
)
battery_energy_capital_cost = _annuity_overnight_to_annualized(
    battery_energy_capex_per_MWh, battery_lifetime_years
)
cap_h2_el = _annuity_overnight_to_annualized(h2_electrolyzer_capex_overnight, h2_chain_lifetime_years)
cap_h2_fc = _annuity_overnight_to_annualized(h2_fuelcell_capex_overnight, h2_chain_lifetime_years)
cap_h2_e = _annuity_overnight_to_annualized(h2_storage_capex_overnight, h2_chain_lifetime_years)

n_st = n_before_opt.copy()

# Carriers / buses for H2
n_st.add("Carrier", "battery")
n_st.add("Carrier", "hydrogen")
n_st.add("Bus", "bus battery", carrier="battery")
n_st.add("Bus", "bus H2", carrier="hydrogen")

# --- Battery (endogenous duration): charger/discharger links + energy store ---
# Split power capex equally across charge/discharge links.
n_st.add(
    "Link",
    "battery charger",
    bus0="electricity bus",
    bus1="bus battery",
    carrier="battery",
    p_nom_extendable=True,
    p_nom=0.0,
    efficiency=battery_eff_store,
    capital_cost=0.5 * battery_power_capital_cost,
    marginal_cost=0.0,
)
n_st.add(
    "Link",
    "battery discharger",
    bus0="bus battery",
    bus1="electricity bus",
    carrier="battery",
    p_nom_extendable=True,
    p_nom=0.0,
    efficiency=battery_eff_dispatch,
    capital_cost=0.5 * battery_power_capital_cost,
    marginal_cost=0.0,
)
n_st.add(
    "Store",
    "battery energy",
    bus="bus battery",
    carrier="battery",
    e_nom_extendable=True,
    e_nom=0.0,
    e_cyclic=True,
    capital_cost=battery_energy_capital_cost,
    marginal_cost=0.0,
)

# --- Hydrogen: electrolyzer (Link) + store + fuel cell (Link) ---
# Electrolyzer: electricity -> H2
n_st.add(
    "Link",
    "electrolyzer",
    bus0="electricity bus",
    bus1="bus H2",
    carrier="hydrogen",
    p_nom_extendable=True,
    p_nom=0.0,
    efficiency=h2_electrolyzer_eff,
    capital_cost=cap_h2_el,
    marginal_cost=0.0,
)

# H2 energy storage (MWh_H2)
n_st.add(
    "Store",
    "H2 storage",
    bus="bus H2",
    e_nom_extendable=True,
    e_nom=0.0,
    e_cyclic=True,
    capital_cost=cap_h2_e,
    marginal_cost=0.0,
)

# Fuel cell: H2 -> electricity
n_st.add(
    "Link",
    "fuel cell",
    bus0="bus H2",
    bus1="electricity bus",
    carrier="hydrogen",
    p_nom_extendable=True,
    p_nom=0.0,
    efficiency=h2_fuelcell_eff,
    capital_cost=cap_h2_fc,
    marginal_cost=0.0,
)

co2_limit = 50_000  # tCO2 (tonnes CO2)


def _optimize_with_fallback(net, label=""):
    solvers = ["gurobi", "highs"]
    last_err = None
    for s in solvers:
        try:
            if s == "gurobi":
                net.optimize(solver_name=s, log_to_console=False, solver_options={"OutputFlag": 0})
            elif s == "highs":
                net.optimize(solver_name=s, log_to_console=False, solver_options={"output_flag": False})
            else:
                net.optimize(solver_name=s, log_to_console=False)
            print(f"{label}Optimization OK with solver={s}")
            return s
        except Exception as e:
            last_err = e
            print(f"{label}Solver {s} failed: {e}")
    raise last_err


Path("figures").mkdir(exist_ok=True)

# %%
#%% Print results (with and without CO2 constraint)
generators = ['hydro', 'nuclear', 'biomass', 'solar', 'onshorewind']
gen_colors = {'hydro': 'royalblue', 'nuclear': 'mediumorchid', 'biomass': 'forestgreen',
              'solar': 'gold', 'onshorewind': 'dodgerblue'}
gen_labels = {'hydro': 'Hydro', 'nuclear': 'Nuclear', 'biomass': 'Biomass',
              'solar': 'Solar', 'onshorewind': 'Onshore Wind'}


def _total_co2_emissions_t(net: pypsa.Network) -> float:
    co2_intensity = net.generators.carrier.map(net.carriers.co2_emissions).fillna(0.0)
    # Generator dispatch is in MWh_el; divide by efficiency to recover primary energy basis.
    primary_input = net.generators_t.p.divide(net.generators.efficiency, axis=1)
    return float(primary_input.mul(co2_intensity, axis=1).sum().sum())


def _co2_shadow_price(net: pypsa.Network) -> float:
    if "co2_limit" not in net.global_constraints.index:
        return float("nan")
    return float(net.global_constraints.at["co2_limit", "mu"])


def _build_summary_tables(net: pypsa.Network, case_name: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    objective_musd = net.objective / 1e6
    avg_price = net.objective / net.loads_t.p_set.sum().sum()
    co2_emissions = _total_co2_emissions_t(net)
    co2_price = _co2_shadow_price(net)

    system_table = pd.DataFrame(
        {
            "Case": [case_name],
            "Objective [M$]": [objective_musd],
            "Electricity price [$/MWh]": [avg_price],
            "CO2 emissions [tCO2]": [co2_emissions],
            "CO2 price [$/tCO2]": [co2_price],
        }
    )

    gen_cap = net.generators.p_nom_opt.rename("Capacity [MW]")
    gen_disp = net.generators_t.p.sum().rename("Dispatch [MWh]")
    gen_table = pd.concat([gen_cap, gen_disp], axis=1).fillna(0.0)

    if len(net.links.index) > 0:
        link_cap = net.links.p_nom_opt.rename("Capacity [MW]")
        link_disp = net.links_t.p0.abs().sum().rename("Dispatch [MWh]")
        links_table = pd.concat([link_cap, link_disp], axis=1).fillna(0.0)
    else:
        links_table = pd.DataFrame(columns=["Capacity [MW]", "Dispatch [MWh]"])

    if len(net.stores.index) > 0:
        store_cap = net.stores.e_nom_opt.rename("Capacity [MWh]")
        store_throughput = net.stores_t.e.diff().abs().sum().fillna(0.0).rename("Dispatch [MWh]")
        stores_table = pd.concat([store_cap, store_throughput], axis=1).fillna(0.0)
    else:
        stores_table = pd.DataFrame(columns=["Capacity [MWh]", "Dispatch [MWh]"])

    return system_table, gen_table, pd.concat(
        {"Links": links_table, "Stores": stores_table},
        axis=0
    )


n_st_no_co2 = n_st.copy()
_optimize_with_fallback(n_st_no_co2, label="[storage, no CO2 cap] ")

n_st_co2 = n_st.copy()
n_st_co2.add(
    "GlobalConstraint",
    "co2_limit",
    type="primary_energy",
    carrier_attribute="co2_emissions",
    sense="<=",
    constant=co2_limit,
)
_optimize_with_fallback(n_st_co2, label="[storage, with CO2 cap] ")

for case_name, net_case in {
    "No CO2 constraint": n_st_no_co2,
    f"With CO2 constraint ({co2_limit:,.0f} tCO2)": n_st_co2,
}.items():
    print(f"\n{'=' * 90}")
    print(case_name)
    print(f"{'=' * 90}")

    system_table, gen_table, storage_table = _build_summary_tables(net_case, case_name)

    print("\nSystem metrics:")
    print(system_table.round(3).to_string(index=False))

    print("\nGenerator capacity and dispatch:")
    print(gen_table.round(3).to_string())

    print("\nStorage technologies (links/stores) capacity and dispatch:")
    print(storage_table.round(3).to_string())

# Plot generation mix as a function of imposed CO2 cap
original_co2_emissions = _total_co2_emissions_t(n_st_no_co2)
co2_caps = np.linspace(0.0, original_co2_emissions, 8)
mix_rows = []

for cap in co2_caps:
    n_cap = n_st.copy()
    n_cap.add(
        "GlobalConstraint",
        "co2_limit",
        type="primary_energy",
        carrier_attribute="co2_emissions",
        sense="<=",
        constant=cap,
    )
    _optimize_with_fallback(n_cap, label=f"[mix vs CO2 cap={cap:,.0f}] ")

    annual_gen = n_cap.generators_t.p[generators].sum()
    total_gen = annual_gen.sum()
    row = {"co2_cap_t": cap, "system_cost_musd": n_cap.objective / 1e6}
    for g in generators:
        row[g] = annual_gen[g] / total_gen if total_gen > 0 else 0.0
    mix_rows.append(row)

mix_df = pd.DataFrame(mix_rows).sort_values("co2_cap_t")
mix_df["co2_cap_mton"] = mix_df["co2_cap_t"] / 1e6

#%% Plot generation mix as a function of imposed CO2 cap
fig, ax = plt.subplots(figsize=(12, 6))
ax.stackplot(
    mix_df["co2_cap_mton"].values,
    [mix_df[g].values for g in generators],
    labels=[gen_labels[g] for g in generators],
    colors=[gen_colors[g] for g in generators],
    alpha=0.9,
)
ax.set_xlabel("Imposed CO2 constraint [Mton CO2]", fontsize=18)
ax.set_ylabel("Generation mix share [-]", fontsize=18)
ax.set_ylim(0, 1)
ax.set_xlim(0, original_co2_emissions / 1e6)
ax.set_title("Generation mix as a function of CO2 constraint", fontsize=20)
ax.tick_params(axis="both", labelsize=14)
ax.legend(
    loc="center left",
    bbox_to_anchor=(0.82, 0.58),  # move left: mid-right placement inside the axes
    fontsize=14,
)
ax.grid(alpha=0.25)

ax2 = ax.twinx()
ax2.plot(
    mix_df["co2_cap_mton"].values,
    mix_df["system_cost_musd"].values,
    color="black",
    linewidth=1.0,
    label="System cost",
)
ax2.set_ylabel("System cost [M$]", color="black", fontsize=18)
ax2.tick_params(axis="y", colors="black", labelsize=14)
ax2.legend(
    loc="center left",
    bbox_to_anchor=(0.82, 0.40),  # stacked below the stackplot legend
    fontsize=14,
)

plt.tight_layout()
fig.savefig("figures/generation_mix_vs_co2_constraint.png", dpi=300, bbox_inches="tight")
plt.show()

# %% 
