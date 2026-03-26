# 46770 Integrated Energy Grids — Course Project Part 1

Techno-economic optimization of the Brazilian power system using [PyPSA](https://pypsa.org/).  
DTU Course 46770, Spring 2026.

## Project overview

The project progressively builds up a model of the Brazilian electricity system:

| Task | Description | Script |
|------|-------------|--------|
| **a) Single-node model** | Capacity expansion and dispatch optimization for the SE region (hydro, biomass, nuclear, wind, solar). Includes weekly dispatch, electricity mix, and duration curves. | `baseModel_singlenode.py` |
| **b) Sensitivity analysis** | Reruns the single-node optimization across 20 weather years (2005–2024) to quantify how inter-annual variability in solar/wind resources affects optimal capacities and generation. | `sensitivity_analysis.py` |
| **c) Storage** | Extends the single-node model with battery and hydrogen storage (electrolyzer → H₂ store → fuel cell) to analyse balancing strategies across intraday and seasonal timescales. | `baseModel_storage.py` |
| **d) Multi-node network** | Four-bus model (N, NE, SE, S) connected by HVAC lines with DC load-flow approximation. Optimises generation and transmission jointly; results verified analytically via incidence and PTDF matrices. | `Network model d).py` |
| **e) PTDF verification** | Hand calculation (pen & paper) of incidence and PTDF matrices to replicate the first-timestep power flows from task d). | — |

## Repository structure

```
.
├── datapreparation.py          # Shared data layer: demand, wind/solar CFs
├── baseModel_singlenode.py     # Task a – single-node capacity optimisation
├── baseModel_storage.py        # Task c – storage extension
├── sensitivity_analysis.py     # Task b – 20-year weather sensitivity
├── Network model d).py         # Task d – multi-node network model
├── plotting.py                 # Quick CF exploration plots
├── Data/
│   ├── demand_brazil.csv
│   └── renewablesNinjaData/
│       ├── ninja-weather-country-BR-wind_speed_area_wtd-merra2.csv
│       └── ninja-weather-country-BR-irradiance_surface_area_wtd-merra2.csv
└── figures/                    # Generated plots (dispatch, mix, storage, etc.)
```

## Setup

### Dependencies

- Python 3.10+
- [PyPSA](https://pypsa.readthedocs.io/)
- pandas, numpy, matplotlib
- [Cartopy](https://scitools.org.uk/cartopy/) (for the network map in task d)
- [Gurobi](https://www.gurobi.com/) solver (academic licence)

Install with:

```bash
pip install pypsa pandas numpy matplotlib cartopy gurobipy
```

### Running

Each script is written in cell-style (`#%%`) and can be run top-to-bottom in an IDE (VS Code, Spyder, etc.) or as a regular Python script:

```bash
python baseModel_singlenode.py
python sensitivity_analysis.py
python baseModel_storage.py
python "Network model d).py"
```

> **Note:** `datapreparation.py` is imported by the other scripts — it does not need to be run separately.

## Data sources

| Dataset | Source |
|---------|--------|
| Hourly regional demand | [ONS Brazil](https://www.ons.org.br/) |
| Wind speed & irradiance | [Renewables.ninja](https://www.renewables.ninja/) (MERRA-2 reanalysis) |
| Technology costs & lifetimes | Literature (see report) |
