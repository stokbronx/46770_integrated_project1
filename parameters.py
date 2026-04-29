capital_cost = dict(  # in $/MW
    hydro=3215000,
    biomass=1900000,
    nuclear=7545000,
    wind=1083000,
    solar=877000,
    gas=682600,
)

opex_cost = dict(  # in $/MW
    hydro=19380,
    biomass=73120,
    nuclear=116000,
    wind=15200,
    solar=13000,
    gas=5610,
)

marginal_cost = dict(  # in $/MWh
    hydro=0,
    biomass=3.25,
    nuclear=3.7,
    wind=0,
    solar=0,
    gas=51.2,
)

lifetime = dict( # in years
    hydro=30,
    biomass=20,
    nuclear=30,
    wind=20,
    solar=25,
    gas=25,
)
import numpy as np
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

