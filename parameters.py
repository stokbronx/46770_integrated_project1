capital_cost = dict(  # in $/MW
    hydro=3215000,
    biomass=1900000,
    nuclear=7545000,
    wind=1083000,
    solar=877000,
    gas=682600,
    heat_pump=932000,   # large air-source HP, $/MW_th
    # Local residential gas boiler (for DHW/space heating):
    # Based on literature value 4422.2 EUR per unit (20-year life) and
    # assuming ~20 kW_th unit size -> ~221 EUR/kW_th = 221,000 EUR/MW_th.
    # Converted at ~1.08 USD/EUR -> ~239,000 USD/MW_th.
    gas_boiler_local=297000,
)

opex_cost = dict(  # in $/MW/year (fixed O&M)
    hydro=19380,
    biomass=73120,
    nuclear=116000,
    wind=15200,
    solar=13000,
    gas=5610,
    heat_pump=capital_cost["heat_pump"] * 0.025,
    # Literature rule-of-thumb: fixed O&M = 2.5% of investment cost/year.
    gas_boiler_local=5975,
)

marginal_cost = dict(  # in $/MWh
    hydro=0,
    biomass=3.25,
    nuclear=3.7,
    wind=0,
    solar=0,
    gas=51.2,
    heat_pump=0,
    # Fuel-only marginal heat cost:
    # p_gas,household,BR ~ 0.176 USD/kWh_fuel  -> 176 USD/MWh_fuel
    # eta_boiler = 0.90  -> 176 / 0.90 = 195.6 USD/MWh_heat
    gas_boiler_local=51.2,
)

gas_efficiency = 0.55

lifetime = dict( # in years
    hydro=30,
    biomass=20,
    nuclear=30,
    wind=20,
    solar=25,
    gas=25,
    heat_pump=20,
    gas_boiler_local=20,
)
import numpy as np
import pandas as pd
def methane_capacity(D=0.6, u_H2=15, P_H2=50*100000, Z=1.31, 
                      R=8.314, M=0.016, T=273+25, e_H2=50):
    """
    Calculate methane flow capacity.
    Parameters:
    D      : Pipe diameter (m)
    u_H2   : Velocity (m/s)
    P_H2   : Pressure (Pa)
    Z      : Compressibility factor
    R      : Gas constant (J/mol·K)
    M      : Molar mass (kg/mol)
    T      : Temperature (K)
    e_H2   : Energy content (MJ/kg)
    Returns:
    c_H2        : Speed of sound (m/s)
    rho_H2      : Density (kg/m³)
    capacity_H2 : Energy flow (MJ/s)
    """
    # Cross-sectional area
    A = np.pi * (D/2)**2

    # Speed of sound
    c_gas = np.sqrt(Z * R * T / M)

    # Density
    rho_gas = P_H2 / c_gas**2

    # Energy capacity
    capacity_gas = rho_gas * A * u_H2 * e_H2

    return c_gas, rho_gas, capacity_gas


# Example usage
c_gas, rho_gas, capacity_gas = methane_capacity()

print("Speed of sound:", c_gas)
print("Density:", rho_gas)
print("Capacity:", capacity_gas)

DISCOUNT_RATE = 0.07

max_capacity_hydro = 40000 # in MW
max_capacity_biomass= 10**10 # in MW

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


def cop_from_temperature(
    temperature_celsius,
    T_sink_celsius=55.0,
    cop_min=1.5,
    cop_max=6.0,
):
    """Time-varying air-source heat-pump COP from ambient temperature.

    Uses the quadratic ASHP regression (Ruhnau et al., 2019):

        COP(ΔT) = 6.08 - 0.09*ΔT + 0.0005*ΔT²
        where ΔT = T_sink - T_source, in °C.

    The returned COP is clipped to [cop_min, cop_max] to keep values in a
    realistic range for system modelling.

    Parameters
    ----------
    temperature_celsius : pandas.Series, pandas.DataFrame, numpy.ndarray, or scalar
        Source-side (ambient outdoor) temperature in degrees Celsius.
    T_sink_celsius : float
        Heat-distribution supply temperature in degrees Celsius (default 55 °C).
    cop_min, cop_max : float
        Lower / upper bound on the returned COP.

    Returns
    -------
    Same container type as input, with COP values.
    """
    if isinstance(temperature_celsius, (pd.Series, pd.DataFrame)):
        delta_t = T_sink_celsius - temperature_celsius
        cop = 6.08 - 0.09 * delta_t + 0.0005 * delta_t**2
        return cop.clip(lower=cop_min, upper=cop_max)

    arr = np.asarray(temperature_celsius, dtype=float)
    delta_t = T_sink_celsius - arr
    cop = 6.08 - 0.09 * delta_t + 0.0005 * delta_t**2
    return np.clip(cop, cop_min, cop_max)

