#%%
import pandas as pd
import pypsa
import importlib
from typing import Optional
import parameters
from datapreparation import (
    demand_north,
    demand_south,
    demand_north_east,
    demand_south_east,
    wind_cf_hourly,
    solar_cf_hourly,
)

importlib.reload(parameters)
from parameters import max_capacity_hydro, annuity, annualized_cost, marginal_cost, methane_capacity


regions = ["BRA-N", "BRA-NE", "BRA-SE", "BRA-S"]
region_cf_map = {"BRA-N": "N", "BRA-S": "S", "BRA-NE": "NE", "BRA-SE": "SE"}
technologies = ["hydro", "biomass", "nuclear", "wind", "solar"]


def build_base_network() -> pypsa.Network:
    n = pypsa.Network()

    n.add(
        "Carrier",
        ["hydro", "biomass", "nuclear", "wind", "solar", "battery", "H2", "gas"],
        nice_name=["Hydro", "Biomass", "Nuclear", "Wind", "Solar", "Battery", "Hydrogen", "Gas"],
        color=["aquamarine", "sienna", "purple", "dodgerblue", "gold", "violet", "green", "gray"],
    )
    n.add("Carrier", "AC")

    n.add("Bus", "bus BRA-N", v_nom=400.0, carrier="AC", x=-60.0, y=-3.0)
    n.add("Bus", "bus BRA-NE", v_nom=400.0, carrier="AC", x=-38.5, y=-12.9)
    n.add("Bus", "bus BRA-SE", v_nom=400.0, carrier="AC", x=-46.6, y=-19.5)
    n.add("Bus", "bus BRA-S", v_nom=400.0, carrier="AC", x=-51.2, y=-30.0)

    n.add("Line", " line N-NE", bus0="bus BRA-N", bus1="bus BRA-NE", x=0.1, r=0.01, carrier="AC", s_nom=1100)
    n.add("Line", " line NE-SE", bus0="bus BRA-NE", bus1="bus BRA-SE", x=0.1, r=0.01, carrier="AC", s_nom=1100)
    n.add("Line", " line SE-S", bus0="bus BRA-SE", bus1="bus BRA-S", x=0.1, r=0.01, carrier="AC", s_nom=1100)
    n.add("Line", " line SE-N", bus0="bus BRA-SE", bus1="bus BRA-N", x=0.1, r=0.01, carrier="AC", s_nom=1100)

    # Gas buses and pipelines (same setup as Network model g).py)
    c_CH4, rho_CH4, capacity_CH4 = methane_capacity()
    for region in regions:
        n.add("Bus", f"gas {region}", carrier="gas")

    for n0, n1 in [("BRA-N", "BRA-NE"), ("BRA-NE", "BRA-SE"), ("BRA-SE", "BRA-S"), ("BRA-SE", "BRA-N")]:
        n.add(
            "Link",
            f"gas pipeline {n0}-{n1}",
            bus0=f"gas {n0}",
            bus1=f"gas {n1}",
            p_nom=0,
            p_nom_extendable=True,
            carrier="gas",
            efficiency=1.0,
            marginal_cost=0.0,
        )

    # Snapshots
    wind_cf = wind_cf_hourly.copy()
    solar_cf = solar_cf_hourly.copy()
    wind_cf.index = pd.to_datetime(wind_cf.index).tz_localize(None)
    solar_cf.index = pd.to_datetime(solar_cf.index).tz_localize(None)
    n.snapshots = wind_cf.index

    # Generators
    hydro_cap = {reg: max_capacity_hydro for reg in regions}
    for region in regions:
        for tech in technologies:
            cap_cost = annualized_cost(tech)
            marg_cost = marginal_cost[tech]

            if tech in ["wind", "solar"]:
                cf = {"wind": wind_cf, "solar": solar_cf}[tech][region_cf_map[region]]
                p_max_pu = cf.reindex(n.snapshots).fillna(0).values
            else:
                p_max_pu = None

            p_nom_max = hydro_cap[region] if tech == "hydro" else None

            n.add(
                "Generator",
                f"{region} {tech}",
                bus=f"bus {region}",
                carrier=tech,
                p_nom=0,
                p_nom_extendable=True,
                p_nom_max=p_nom_max,
                capital_cost=cap_cost,
                marginal_cost=marg_cost,
                p_max_pu=p_max_pu,
            )

    # Gas plants
    for region in regions:
        n.add(
            "Link",
            f"{region} gas plant",
            bus0=f"gas {region}",
            bus1=f"bus {region}",
            carrier="gas",
            efficiency=0.55,
            p_nom=0,
            p_nom_extendable=True,
            capital_cost=annualized_cost("gas"),
            marginal_cost=marginal_cost["gas"],
        )

    # Battery storage
    battery_lifetime = 15
    battery_power_cost = 65_000
    battery_energy_cost = 230_000
    power_capital_cost = annuity(battery_lifetime, 0.07) * battery_power_cost
    energy_capital_cost = annuity(battery_lifetime, 0.07) * battery_energy_cost

    for region in regions:
        n.add(
            "StorageUnit",
            f"{region} battery",
            bus=f"bus {region}",
            carrier="battery",
            p_nom_extendable=True,
            p_nom=0,
            max_hours=4.0,
            efficiency_store=0.95,
            efficiency_dispatch=0.95,
            standing_loss=0.0005,
            capital_cost=power_capital_cost + energy_capital_cost,
            marginal_cost=0.0,
            cyclic_state_of_charge=True,
        )

    # Loads
    demand = {
        "BRA-N": demand_north,
        "BRA-S": demand_south,
        "BRA-NE": demand_north_east,
        "BRA-SE": demand_south_east,
    }
    for region, demand_ts in demand.items():
        n.add(
            "Load",
            f"load {region}",
            bus=f"bus {region}",
            p_set=demand_ts.reindex(n.snapshots).fillna(0),
            overwrite=True,
        )

    return n


co2_intensity_t_per_mwh_th = {
    "hydro": 0.0,
    "biomass": 0.210,
    "nuclear": 0.0,
    "wind": 0.0,
    "solar": 0.0,
    "battery": 0.0,
    "H2": 0.0,
    "gas": 0.19,
    "AC": 0.0,
}


def _set_carrier_emissions(net: pypsa.Network) -> None:
    for carrier, value in co2_intensity_t_per_mwh_th.items():
        if carrier in net.carriers.index:
            net.carriers.at[carrier, "co2_emissions"] = value


def _ensure_gas_supply(net: pypsa.Network) -> None:
    for reg in regions:
        name = f"{reg} gas supply"
        if name not in net.generators.index:
            net.add(
                "Generator",
                name,
                bus=f"gas {reg}",
                carrier="gas",
                p_nom_extendable=True,
                p_nom=0.0,
                marginal_cost=0.0,
                capital_cost=0.0,
            )


def _prepare_co2_accounting(net: pypsa.Network) -> None:
    for cname, nice in [("gas_network", "Gas network"), ("gas_plant", "Gas plant")]:
        if cname not in net.carriers.index:
            net.add("Carrier", cname, nice_name=nice, co2_emissions=0.0)
        else:
            net.carriers.at[cname, "co2_emissions"] = 0.0

    if not net.links.empty:
        pipe_mask = net.links.index.to_series().str.contains("gas pipeline", regex=False)
        plant_mask = net.links.index.to_series().str.contains("gas plant", regex=False)
        if pipe_mask.any():
            net.links.loc[pipe_mask.values, "carrier"] = "gas_network"
        if plant_mask.any():
            net.links.loc[plant_mask.values, "carrier"] = "gas_plant"


def _optimize_with_fallback(net: pypsa.Network, label: str = "") -> str:
    return _optimize_with_cap_fallback(net, co2_cap_t=None, label=label)


def _build_custom_co2_extra_functionality(co2_cap_t: float):
    def _extra_functionality(n: pypsa.Network, snapshots) -> None:
        gen_p = n.model["Generator-p"]

        gas_supply = n.generators.index[
            n.generators.index.to_series().str.contains(" gas supply", regex=False)
        ].tolist()
        biomass_gens = n.generators.index[n.generators.carrier == "biomass"].tolist()

        gas_expr = 0.0
        if len(gas_supply) > 0:
            gas_expr = 0.19 * gen_p.loc[:, gas_supply].sum()

        biomass_expr = 0.0
        if len(biomass_gens) > 0:
            biomass_expr = 0.210 * gen_p.loc[:, biomass_gens].sum()

        total_emissions_expr = gas_expr + biomass_expr
        n.model.add_constraints(total_emissions_expr <= co2_cap_t, name="co2_cap_custom")

    return _extra_functionality


def _optimize_with_cap_fallback(net: pypsa.Network, co2_cap_t: Optional[float], label: str = "") -> str:
    for solver in ["gurobi", "highs"]:
        try:
            if co2_cap_t is None:
                net.optimize(solver_name=solver)
            else:
                net.optimize(
                    solver_name=solver,
                    extra_functionality=_build_custom_co2_extra_functionality(co2_cap_t),
                )
            print(f"{label}Optimization OK with solver={solver}")
            return solver
        except Exception as exc:
            print(f"{label}Solver {solver} failed: {exc}")
    raise RuntimeError(f"{label}All solvers failed.")


def _total_emissions_tco2(net: pypsa.Network) -> dict[str, float]:
    gas_t = 0.0
    biomass_t = 0.0

    gas_supply = net.generators.index[
        net.generators.index.to_series().str.contains(" gas supply", regex=False)
    ]
    if len(gas_supply) > 0:
        gas_mwh_th = float(net.generators_t.p[gas_supply].sum().sum())
        gas_t = gas_mwh_th * float(net.carriers.at["gas", "co2_emissions"])

    biomass_gens = net.generators.index[net.generators.carrier == "biomass"]
    if len(biomass_gens) > 0:
        biomass_mwh_el = float(net.generators_t.p[biomass_gens].sum().sum())
        biomass_t = biomass_mwh_el * 0.210

    return {
        "gas_tco2": float(gas_t),
        "biomass_tco2": float(biomass_t),
        "total_tco2": float(gas_t + biomass_t),
    }


def _co2_shadow_price(net: pypsa.Network) -> float:
    try:
        dual_val = net.model.constraints["co2_cap_custom"].dual
        if hasattr(dual_val, "item"):
            return abs(float(dual_val.item()))
        return abs(float(dual_val))
    except Exception:
        return float("nan")


network_h_template = build_base_network()
_set_carrier_emissions(network_h_template)
_ensure_gas_supply(network_h_template)
_prepare_co2_accounting(network_h_template)

network_h_nocap = network_h_template.copy()
_optimize_with_fallback(network_h_nocap, label="[H no cap] ")
baseline_em = _total_emissions_tco2(network_h_nocap)
baseline_emissions_t = baseline_em["total_tco2"]

target_reduction = 0.70
co2_cap_t = (1.0 - target_reduction) * baseline_emissions_t

network_h_cap = network_h_template.copy()
_optimize_with_cap_fallback(network_h_cap, co2_cap_t=co2_cap_t, label="[H with cap] ")

cap_em = _total_emissions_tco2(network_h_cap)
implied_co2_price = _co2_shadow_price(network_h_cap)

print("\n" + "=" * 80)
print("H) CO2 TARGET AND IMPLIED CO2 PRICE")
print("=" * 80)
print(f"Baseline emissions (no cap): {baseline_em['total_tco2']:,.0f} tCO2")
print(f"  - gas: {baseline_em['gas_tco2']:,.0f} tCO2")
print(f"  - biomass: {baseline_em['biomass_tco2']:,.0f} tCO2")
print(f"Target reduction: {100 * target_reduction:.1f}%")
print(f"Applied CO2 cap: {co2_cap_t:,.0f} tCO2")
print(f"Emissions with cap: {cap_em['total_tco2']:,.0f} tCO2")
print(f"  - gas: {cap_em['gas_tco2']:,.0f} tCO2")
print(f"  - biomass: {cap_em['biomass_tco2']:,.0f} tCO2")
print(f"Implied CO2 price (shadow price mu): {implied_co2_price:,.2f} $/tCO2")
print("\nCustom CO2 cap formulation used:")
print("  total_emissions = 0.19 * sum(gas supply dispatch) + 0.210 * sum(biomass dispatch)")
print(f"  constraint: total_emissions <= {co2_cap_t:,.0f} tCO2")
print(
    "System cost [M$] - no cap / with cap: "
    f"{network_h_nocap.objective / 1e6:,.2f} / {network_h_cap.objective / 1e6:,.2f}"
)
print("=" * 80)
