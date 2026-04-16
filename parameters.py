capital_cost = dict(  # in $/MW
    hydro=3215000,
    biomass=1300000,
    nuclear=7545000,
    wind=1083000,
    solar=877000,
)

opex_cost = dict(  # in $/MW
    hydro=19380,
    biomass=73120,
    nuclear=116000,
    wind=15200,
    solar=13000,
)

marginal_cost = dict(  # in $/MWh
    hydro=0,
    biomass=3.25,
    nuclear=3.7,
    wind=0,
    solar=0,
)

lifetime = dict(
    hydro=30,
    biomass=20,
    nuclear=30,
    wind=20,
    solar=25,
)

DISCOUNT_RATE = 0.07

max_capacity_hydro = 40000


def annuity(n, r):
    """Calculate the annuity factor for an asset with lifetime n years and
    discount rate r."""
    if r > 0:
        return r / (1.0 - 1.0 / (1.0 + r) ** n)
    else:
        return 1 / n


def annualized_cost(tech):
    """Annualized capital cost + fixed O&M for a technology ($/MW/year)."""
    return annuity(lifetime[tech], DISCOUNT_RATE) * capital_cost[tech] + opex_cost[tech]
