import numpy as np
import matplotlib.pyplot as plt
from pvlib import pvsystem, modelchain, location, iotools
import pandas as pd
import calendar

# ------------------------------
# 🌍 Global Parameters
# ------------------------------
FREQ = '1h'  # Time step frequency ('0.5h' or '1h')
TIME_SHIFT = 0  # Time shift in hours (set to 0 to avoid plotting issues)
LATITUDE = 40
LONGITUDE = -80

USE_CUSTOM_LOCATION = True
USE_REAL_WEATHER = True
PLOT_ENERGY_REPORTS = True
SIMULATE_BATTERY = True
SIMULATE_SMART_GRID = True

BATTERY_CAPACITY_KWH = 10.0
BATTERY_CHARGE_EFF = 0.95
BATTERY_DISCHARGE_EFF = 0.95

GRID_SUPPORT_LIMIT_KW = 2.0

# ------------------------
# 🔧 Tower and Panel Specs
# ------------------------
tower_diameter = 0.6
tower_height = 12

panel_width = 0.1
panel_height = 1.0
power_density = 175

num_panels_circumference = int(np.ceil((np.pi * tower_diameter) / panel_width))
num_panels_height = int(tower_height / panel_height)

panel_area_total = num_panels_circumference * num_panels_height * panel_width * panel_height
total_dc_power_kw = (panel_area_total * power_density) / 1000

panel_orientations = np.linspace(0, 360, num_panels_circumference, endpoint=False)

# ------------------------
# ☀️ Location and Simulation
# ------------------------
loc = location.Location(latitude=LATITUDE, longitude=LONGITUDE) if USE_CUSTOM_LOCATION else location.Location(latitude=40, longitude=-80)

array_kwargs = dict(
    module_parameters=dict(pdc0=1, gamma_pdc=-0.004),
    temperature_model_parameters=dict(a=-3.56, b=-0.075, deltaT=3)
)

arrays = [
    pvsystem.Array(
        mount=pvsystem.FixedMount(90, az),
        name=f'Array {az:.1f}°',
        **array_kwargs
    ) for az in panel_orientations
]

system = pvsystem.PVSystem(
    arrays=arrays,
    inverter_parameters=dict(pdc0=total_dc_power_kw)
)

mc = modelchain.ModelChain(system, loc, aoi_model='physical', spectral_model='no_loss')

reference_date = '2019-01-01'
time_range = pd.date_range(f'{reference_date} 00:00', f'{reference_date} 23:00', freq=FREQ, tz='Etc/GMT+0')
times_local = time_range.tz_convert(loc.tz)
time_of_day = times_local.strftime('%H:%M')
time_of_day_shifted = (times_local + pd.Timedelta(hours=TIME_SHIFT)).strftime('%H:%M')

results_raw = pd.DataFrame(index=time_of_day)
monthly_energy_kwh = {}

for month in range(1, 13):
    times = time_range.map(lambda t: t.replace(month=month))

    if USE_REAL_WEATHER:
        try:
            weather, metadata_list, metadata_dict, _ = iotools.get_pvgis_tmy(loc.latitude, loc.longitude, map_variables=True)
            weather = weather.loc[times]
        except:
            weather = loc.get_clearsky(times)
    else:
        weather = loc.get_clearsky(times)

    mc.run_model(weather)
    total_dc_output = sum(mc.results.dc)

    month_name = calendar.month_name[month]
    results_raw[month_name] = total_dc_output.values

    timestep_hours = pd.Timedelta(FREQ).total_seconds() / 3600
    energy_kwh = total_dc_output.sum() * timestep_hours
    monthly_energy_kwh[month_name] = energy_kwh

# -----------------------------------
# Battery Simulation
# -----------------------------------
results_battery = results_raw.copy()
if SIMULATE_BATTERY:
    for month in results_raw.columns:
        soc = 0.0
        adjusted_output = []
        for power in results_raw[month]:
            energy = power * (pd.Timedelta(FREQ).total_seconds() / 3600)
            if energy > 0:
                excess_energy = max(0, energy - 0.5)
                charge = min(excess_energy * BATTERY_CHARGE_EFF, BATTERY_CAPACITY_KWH - soc)
                soc += charge
                net_energy = energy - charge
            else:
                net_energy = energy

            if net_energy < 0.5:
                needed = 0.5 - net_energy
                discharge = min(needed / BATTERY_DISCHARGE_EFF, soc)
                soc -= discharge
                net_energy += discharge * BATTERY_DISCHARGE_EFF

            adjusted_output.append(net_energy / (pd.Timedelta(FREQ).total_seconds() / 3600))
        results_battery[month] = adjusted_output
else:
    results_battery = None

# -----------------------------------
# Smart Grid Simulation
# -----------------------------------
results_smart_grid = results_battery.copy() if results_battery is not None else results_raw.copy()

if SIMULATE_SMART_GRID:
    for month in results_smart_grid.columns:
        adjusted_output = []
        for power_kw in results_smart_grid[month]:
            load_kw = 1.0
            if power_kw < load_kw:
                support = min(GRID_SUPPORT_LIMIT_KW, load_kw - power_kw)
                adjusted_output.append(power_kw + support)
            else:
                adjusted_output.append(power_kw)
        results_smart_grid[month] = adjusted_output
else:
    results_smart_grid = None

# -----------------------
# 📊 Plotting section
# -----------------------

markers = ['o', 's', 'D', '^', 'v', '<', '>', 'p', '*', 'h', 'H', 'X']
colors = plt.cm.get_cmap('tab10', 12)

def plot_monthly_profiles(df, title_prefix):
    fig, ax = plt.subplots(figsize=(12, 8))
    for month in range(1, 13):
        month_name = calendar.month_name[month]
        ax.plot(time_of_day, df[month_name],
                marker=markers[month - 1], color=colors(month - 1), label=month_name, linestyle='-')
    ax.set_xlabel('Time of Day')
    ax.set_ylabel('Total System Output (kW)')
    ax.set_title(f'{title_prefix} - Energy Production for One Day in Each Month')
    ax.legend(title="Month", loc='upper left', bbox_to_anchor=(1, 1))
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.tight_layout()
    plt.show()

def plot_normalized_profiles(df, title_prefix):
    fig, ax = plt.subplots(figsize=(12, 8))
    for month in range(1, 13):
        month_name = calendar.month_name[month]
        normalized_output = df[month_name] / df[month_name].max()
        ax.plot(time_of_day, normalized_output,
                marker=markers[month - 1], color=colors(month - 1), label=month_name, linestyle='-')
    ax.set_xlabel('Time of Day')
    ax.set_ylabel('Normalized System Output')
    ax.set_title(f'{title_prefix} - Normalized Energy Production for One Day in Each Month')
    ax.legend(title="Month", loc='upper left', bbox_to_anchor=(1, 1))
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.tight_layout()
    plt.show()

plot_monthly_profiles(results_raw, "Raw PV System Output")
plot_normalized_profiles(results_raw, "Raw PV System Output")

if SIMULATE_BATTERY and results_battery is not None:
    plot_monthly_profiles(results_battery, "With Battery Simulation")
    plot_normalized_profiles(results_battery, "With Battery Simulation")

if SIMULATE_SMART_GRID and results_smart_grid is not None:
    plot_monthly_profiles(results_smart_grid, "With Battery + Smart Grid Simulation")
    plot_normalized_profiles(results_smart_grid, "With Battery + Smart Grid Simulation")

# --------------------------
# 📊 Additional Energy Plots
# --------------------------
if PLOT_ENERGY_REPORTS:
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(monthly_energy_kwh.keys(), monthly_energy_kwh.values(), color='skyblue')
    ax.set_ylabel("Energy (kWh)")
    ax.set_title("Monthly Energy Production (Raw PV System Output)")
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    total_annual_energy = sum(monthly_energy_kwh.values())
    print(f"\n🔋 Total Annual Energy Production (Raw PV System Output): {total_annual_energy:.2f} kWh\n")
