#%% IMPORT
import pandas as pd
pd.options.mode.string_storage = "python"
import pypsa
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


# %% Optimize (baseline — no storage)
# Keep an unfixed copy so we can run part (C) as a joint re-optimization with storage.
n_before_opt = n.copy()

n.optimize(solver_name="gurobi")
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

# Battery capex (part C only)
battery_capex_per_kW = 450  # $/kW
battery_capex_per_MW = battery_capex_per_kW * 1000  # $/MW

# --- Economic / technical assumptions (aligned with report + course examples) ---
OM_FRAC = 0.033

battery_lifetime_years = 15
battery_max_hours = 4.0
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


battery_capital_cost = _annuity_overnight_to_annualized(battery_capex_per_MW, battery_lifetime_years)
cap_h2_el = _annuity_overnight_to_annualized(h2_electrolyzer_capex_overnight, h2_chain_lifetime_years)
cap_h2_fc = _annuity_overnight_to_annualized(h2_fuelcell_capex_overnight, h2_chain_lifetime_years)
cap_h2_e = _annuity_overnight_to_annualized(h2_storage_capex_overnight, h2_chain_lifetime_years)

n_st = n_before_opt.copy()

# Carriers / buses for H2
n_st.add("Carrier", "battery")
n_st.add("Carrier", "hydrogen")
n_st.add("Bus", "bus H2", carrier="hydrogen")

# --- Battery (StorageUnit): 4h duration, ~90% round-trip via 0.95 * 0.95 ---
n_st.add(
    "StorageUnit",
    "battery",
    bus="electricity bus",
    carrier="battery",
    p_nom_extendable=True,
    p_nom=0.0,
    max_hours=battery_max_hours,
    efficiency_store=battery_eff_store,
    efficiency_dispatch=battery_eff_dispatch,
    capital_cost=battery_capital_cost,
    marginal_cost=0.0,
    cyclic_state_of_charge=True,
)

# --- Hydrogen: electrolyzer (Link) + store + fuel cell (Link) ---
# Electrolyzer: electricity -> H2
n_st.add(
    "Link",
    "electrolyzer",
    bus0="electricity bus",
    bus1="bus H2",
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
    p_nom_extendable=True,
    p_nom=0.0,
    efficiency=h2_fuelcell_eff,
    capital_cost=cap_h2_fc,
    marginal_cost=0.0,
)


def _optimize_with_fallback(net, label=""):
    solvers = ["gurobi", "highs"]
    last_err = None
    for s in solvers:
        try:
            net.optimize(solver_name=s)
            print(f"{label}Optimization OK with solver={s}")
            return s
        except Exception as e:
            last_err = e
            print(f"{label}Solver {s} failed: {e}")
    raise last_err


_optimize_with_fallback(n_st, label="[with storage] ")

Path("figures").mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Part (C): systematic comparison — baseline vs with storage
# ---------------------------------------------------------------------------
total_load_st = n_st.loads_t.p_set.sum().sum()
total_load_base = n.loads_t.p_set.sum().sum()

print("\n" + "=" * 72)
print("PART (C) — BASELINE vs WITH STORAGE (optimal configuration & system cost)")
print("=" * 72)

print(f"\n{'Metric':<42} {'No storage':>14} {'With storage':>14}")
print("-" * 72)
print(f"{'Total system cost (objective) [M$]':<42} {n.objective/1e6:>14.4f} {n_st.objective/1e6:>14.4f}")
print(f"{'Average cost of electricity [$/MWh]':<42} {n.objective/total_load_base:>14.2f} {n_st.objective/total_load_st:>14.2f}")

cap_base = n.generators.p_nom_opt
cap_st = n_st.generators.p_nom_opt
cap_delta = cap_st - cap_base
print("\n--- Optimal generator capacities [MW]: Δ = with_storage − baseline ---")
comp_cap = pd.DataFrame({"baseline_MW": cap_base, "with_storage_MW": cap_st, "delta_MW": cap_delta})
print(comp_cap.round(2).to_string())

print("\n--- Optimal storage & H2 chain (with storage only) ---")
if not n_st.storage_units.empty:
    print(n_st.storage_units[["p_nom_opt"]].to_string())
if not n_st.stores.empty:
    print(n_st.stores[["e_nom_opt"]].to_string())
if not n_st.links.empty:
    print(n_st.links[["p_nom_opt"]].to_string())

# ---------------------------------------------------------------------------
# Annual energy flows — interpret intraday (battery) vs longer (H2) balancing
# ---------------------------------------------------------------------------

def _annual_mwh(series):
    """PyPSA time series are per snapshot (1 h); sum ≈ MWh/year."""
    return float(series.sum())


# Battery: use dispatch/store if available, else net p
su_t = n_st.storage_units_t
if "battery" in n_st.storage_units.index:
    try:
        e_dis = _annual_mwh(su_t.p_dispatch["battery"])
        e_ch = _annual_mwh(su_t.p_store["battery"])
    except (KeyError, AttributeError, TypeError):
        p = su_t.p["battery"]
        e_dis = _annual_mwh(p.clip(lower=0.0))
        e_ch = _annual_mwh((-p).clip(lower=0.0))
    print("\n--- Battery (annual energy, MWh) ---")
    print(f"  Discharge to grid (approx.): {e_dis:,.0f}")
    print(f"  Charge from grid (approx.): {e_ch:,.0f}")

# H2: link power at electricity bus; store energy inventory
if "electrolyzer" in n_st.links.index:
    # Electricity consumed by electrolyzer ~ -p0 on electricity bus (sign depends on convention)
    el_p0 = n_st.links_t.p0["electrolyzer"]
    print("\n--- Hydrogen — electrolyzer (annual, MWh elec) ---")
    print(f"  Electricity use (sum |min(0,p0)|): {_annual_mwh((-el_p0).clip(lower=0.0)):,.0f}")
if "fuel cell" in n_st.links.index:
    fc_p1 = n_st.links_t.p1["fuel cell"]
    print("--- Hydrogen — fuel cell (annual, MWh elec out) ---")
    print(f"  Electricity supplied (sum max(p1,0)): {_annual_mwh(fc_p1.clip(lower=0.0)):,.0f}")
if "H2 storage" in n_st.stores.index:
    e_level = n_st.stores_t.e["H2 storage"]
    print("--- H2 storage energy inventory ---")
    print(f"  Mean state [MWh_H2]: {e_level.mean():,.0f}")
    print(f"  Min / max [MWh_H2]: {e_level.min():,.0f} / {e_level.max():,.0f}")
    # Simple seasonal proxy: range over rolling 24*7 h (~week) means
    roll = e_level.rolling(24 * 7, min_periods=1).mean()
    print(f"  Rolling 7-d mean — min / max: {roll.min():,.0f} / {roll.max():,.0f}")

# ---------------------------------------------------------------------------
# Figures for report: one PNG per figure (no subplots); no GUI pop-ups
# ---------------------------------------------------------------------------
gen_names = ["hydro", "nuclear", "biomass", "solar", "onshorewind"]


def _plot_partc_week_separate_files(sl, title_season: str, file_prefix: str):
    """
    Save separate images: generation, battery power, battery SOC, H2 power, H2 energy.
    file_prefix e.g. 'figures/partC_summer' -> partC_summer_gen_demand.png, ...
    """
    base = Path(file_prefix)
    base.parent.mkdir(parents=True, exist_ok=True)

    # --- 1) Generation + demand (single figure) ---
    fig, ax = plt.subplots(figsize=(14, 5))
    dispatch = n_st.generators_t.p.loc[sl, gen_names]
    active = [g for g in gen_names if dispatch[g].sum() > 0]
    if active:
        ax.stackplot(
            dispatch.index,
            dispatch[active].values.T,
            labels=[gen_labels[g] for g in active],
            colors=[gen_colors[g] for g in active],
            alpha=0.85,
        )
    ax.plot(n_st.loads_t.p_set.loc[sl, "load"], color="black", linewidth=1.5, label="Demand")
    ax.set_ylabel("Power [MW]")
    ax.set_xlabel("Time")
    ax.set_title(f"{title_season} — generation & demand (with storage)")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    fig.autofmt_xdate()
    plt.tight_layout()
    _savefig_close_partc(fig, f"{file_prefix}_gen_demand.png")

    # --- 2) Battery power only (single y-axis) ---
    if "battery" in n_st.storage_units.index:
        fig, ax = plt.subplots(figsize=(14, 4))
        try:
            dis = su_t.p_dispatch.loc[sl, "battery"]
            ch = su_t.p_store.loc[sl, "battery"]
            ax.plot(dis.index, dis.values, color="darkviolet", label="Discharge [MW]", linewidth=1.2)
            ax.plot(ch.index, ch.values, color="mediumpurple", label="Charge [MW]", linewidth=1.2)
        except (KeyError, AttributeError, TypeError):
            p = su_t.p.loc[sl, "battery"]
            ax.plot(p.index, p.clip(lower=0.0).values, color="darkviolet", label="Discharge (net) [MW]", linewidth=1.2)
            ax.plot(p.index, (-p).clip(lower=0.0).values, color="mediumpurple", label="Charge (net) [MW]", linewidth=1.2)
        ax.set_ylabel("Power [MW]")
        ax.set_xlabel("Time")
        ax.set_title(f"{title_season} — battery charge / discharge")
        ax.legend(loc="upper right", fontsize=8)
        fig.autofmt_xdate()
        plt.tight_layout()
        _savefig_close_partc(fig, f"{file_prefix}_battery_power.png")

        # --- 3) Battery SOC (own figure — no twin axis with other series) ---
        try:
            soc = su_t.state_of_charge.loc[sl, "battery"]
            fig, ax = plt.subplots(figsize=(14, 4))
            ax.fill_between(soc.index, soc.values, alpha=0.3, color="gray")
            ax.plot(soc.index, soc.values, color="dimgray", linewidth=1.0, label="SOC")
            ax.set_ylabel("State of charge [MWh]")
            ax.set_xlabel("Time")
            ax.set_title(f"{title_season} — battery state of charge")
            ax.legend(loc="upper right", fontsize=8)
            fig.autofmt_xdate()
            plt.tight_layout()
            _savefig_close_partc(fig, f"{file_prefix}_battery_soc.png")
        except (KeyError, AttributeError, TypeError):
            pass

    # --- 4) H2: link powers (raw PyPSA — avoid clipping that hides small flows) ---
    if "electrolyzer" in n_st.links.index or "fuel cell" in n_st.links.index:
        fig, ax = plt.subplots(figsize=(14, 4))
        if "electrolyzer" in n_st.links.index:
            p0_el = n_st.links_t.p0.loc[sl, "electrolyzer"]
            ax.plot(p0_el.index, p0_el.values, color="teal", linewidth=1.2, label="Electrolyzer bus0 power p0 [MW]")
        if "fuel cell" in n_st.links.index:
            p1_fc = n_st.links_t.p1.loc[sl, "fuel cell"]
            ax.plot(p1_fc.index, p1_fc.values, color="coral", linewidth=1.2, label="Fuel cell bus1 power p1 [MW]")
        ax.axhline(0.0, color="k", linewidth=0.5, alpha=0.5)
        ax.set_ylabel("Power [MW]")
        ax.set_xlabel("Time")
        ax.set_title(f"{title_season} — hydrogen links (raw solver output)")
        ax.legend(loc="upper right", fontsize=8)
        fig.autofmt_xdate()
        plt.tight_layout()
        _savefig_close_partc(fig, f"{file_prefix}_h2_link_power.png")

    # --- 5) H2 storage energy (separate figure) ---
    if "H2 storage" in n_st.stores.index:
        e = n_st.stores_t.e.loc[sl, "H2 storage"]
        fig, ax = plt.subplots(figsize=(14, 4))
        ax.plot(e.index, e.values, color="olive", linewidth=1.0)
        ax.set_ylabel("Stored energy [MWh]")
        ax.set_xlabel("Time")
        ax.set_title(f"{title_season} — H2 storage energy level")
        fig.autofmt_xdate()
        plt.tight_layout()
        _savefig_close_partc(fig, f"{file_prefix}_h2_storage_energy.png")


_plot_partc_week_separate_files(
    slice("2024-01-07", "2024-01-13"),
    "Summer week (Jan, Brazil)",
    "figures/partC_summer",
)
_plot_partc_week_separate_files(
    slice("2024-07-01", "2024-07-07"),
    "Winter week (Jul, Brazil)",
    "figures/partC_winter",
)

# Annual mix: two separate pie charts (not side-by-side in one image)
mix_base = n.generators_t.p.sum()
mix_st = n_st.generators_t.p.sum()

for mix, ttl, out in [
    (mix_base, "Annual generation — baseline (no storage)", "figures/partC_mix_baseline.png"),
    (mix_st, "Annual generation — with storage", "figures/partC_mix_with_storage.png"),
]:
    fig, ax = plt.subplots(figsize=(6, 6))
    labels_m = [gen_labels[g] for g in gen_names if mix[g] > 0]
    sizes_m = [mix[g] for g in gen_names if mix[g] > 0]
    cols_m = [gen_colors[g] for g in gen_names if mix[g] > 0]
    ax.pie(
        sizes_m,
        labels=labels_m,
        colors=cols_m,
        autopct=lambda p: f"{p:.1f}%" if p >= 1 else "",
        wedgeprops={"linewidth": 0},
    )
    ax.axis("equal")
    #ax.set_title(ttl)
    plt.tight_layout()
    _savefig_close_partc(fig, out)

# Annual mix: combined baseline vs storage (same as before, now with % labels)
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
for ax, mix, ttl in [
    (axes[0], mix_base, "Annual generation — baseline (no storage)"),
    (axes[1], mix_st, "Annual generation — with storage"),
]:
    labels_m = [gen_labels[g] for g in gen_names if mix[g] > 0]
    sizes_m = [mix[g] for g in gen_names if mix[g] > 0]
    cols_m = [gen_colors[g] for g in gen_names if mix[g] > 0]
    ax.pie(
        sizes_m,
        labels=labels_m,
        colors=cols_m,
        autopct=lambda p: f"{p:.1f}%" if p >= 1 else "",
        wedgeprops={"linewidth": 0},
    )
    ax.axis("equal")
    ax.set_title(ttl)
plt.suptitle("Part (C): impact on annual electricity mix (generators)", y=1.02)
plt.tight_layout()
_savefig_close_partc(fig, "figures/partC_mix_baseline_vs_storage.png")

# Report-ready bullet summary (paste into discussion)
print("\n" + "=" * 72)
print("PART (C) — DISCUSSION SNIPPET (strategies & time scales)")
print("=" * 72)
print("""
• Intraday: BESS (4 h) shifts energy within the day — compare battery charge/discharge
  plots to solar/demand; it reduces need for instant thermal/peaking response.
• Multi-hour to seasonal: H2 store energy level can evolve over many days/weeks if
  electrolyzer + fuel cell are used; interpret H2 tank min/max and rolling means vs battery.
• Optimal configuration: compare the table of generator ΔMW and installed MW of battery /
  electrolyzer / fuel cell / H2 energy to describe how storage displaces or complements
  hydro/wind/solar in your run.
• One-year horizon: true seasonal storage is only partially visible in 1 year; state how
  H2 still provides longer buffering than the 4 h battery if e_nom_opt is large.
""")
print(
    "Figures saved (part C, one file per plot):\n"
    "  figures/partC_summer_gen_demand.png, partC_summer_battery_power.png, partC_summer_battery_soc.png,\n"
    "  partC_summer_h2_link_power.png, partC_summer_h2_storage_energy.png\n"
    "  figures/partC_winter_*.png (same pattern)\n"
    "  figures/partC_mix_baseline.png, figures/partC_mix_with_storage.png"
)
print("=" * 72)

# %%
