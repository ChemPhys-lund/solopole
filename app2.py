import numpy as np
import matplotlib.pyplot as plt
from pvlib import pvsystem, modelchain, location, iotools
import pandas as pd
import calendar

# === GLOBAL SETTINGS ===
# Location & simulation
CUSTOM_LATITUDE = 40
CUSTOM_LONGITUDE = -80
USE_CUSTOM_LOCATION = True
USE_REAL_WEATHER = True

# Battery simulation
SIMULATE_BATTERY = True
BATTERY_CAPACITY_KWH = 10.0
BATTERY_CHARGE_EFFICIENCY = 0.95
BATTERY_DISCHARGE_EFFICIENCY = 0.95

# Smart grid simulation
SIMULATE_SMART_GRID = True
GRID_SUPPORT_LIMIT_KW = 2.0

# Tower and panel specs
TOWER_DIAMETER = 0.6  # meters
TOWER_HEIGHT = 12  # meters
PANEL_WIDTH = 0.1  # meters
PANEL_HEIGHT = 1.0  # meters
POWER_DENSITY = 175  # W/m^2

# Simulation time step and time shift for display
TIME_STEP = '1h'  # Use lowercase 'h' as requested
TIME_SHIFT = 0  # hours; 0 means no shift for display

# === PREPARE LOCATION AND TIME RANGE ===
if USE_CUSTOM_LOCATION:
    loc = location.Location(latitude=CUSTOM_LATITUDE, longitude=CUSTOM_LONGITUDE)
else:
    loc = location.Location(latitude=40, longitude=-80)

reference_date = '2019-01-01'
time_range = pd.date_range(f'{reference_date} 00:00', f'{reference_date} 23:00',
                           freq=TIME_STEP, tz='Etc/GMT+5')
times_local = time_range.tz_convert(loc.tz)

# Format time of day for display (with optional time shift)
time_of_day = (times_local + pd.Timedelta(hours=TIME_SHIFT)).strftime('%H:%M')

# === PANEL ARRAY CALCULATIONS ===
num_panels_circumference = int(np.ceil((np.pi * TOWER_DIAMETER) / PANEL_WIDTH))
num_panels_height = int(TOWER_HEIGHT / PANEL_HEIGHT)
panel_area_total = num_panels_circumference * num_panels_height * PANEL_WIDTH * PANEL_HEIGHT
total_dc_power_kw = (panel_area_total * POWER_DENSITY) / 1000

panel_orientations = np.linspace(0, 360, num_panels_circumference, endpoint=False)

array_kwargs = dict(
    module_parameters=dict(pdc0=1, gamma_pdc=-0.004),
    temperature_model_parameters=dict(a=-3.56, b=-0.075, deltaT=3)
)

arrays = [
    pvsystem.Array(
        mount=pvsystem.FixedMount(90, az),
        name=f'Array {az:.1f}°',
        **array_kwargs
    )
    for az in panel_orientations
]

system = pvsystem.PVSystem(
    arrays=arrays,
    inverter_parameters=dict(pdc0=total_dc_power_kw)
)

mc = modelchain.ModelChain(system, loc, aoi_model='physical', spectral_model='no_loss')

# === SIMULATION STORAGE ===
results_raw = pd.DataFrame(index=time_of_day)
monthly_energy_kwh = {}

# === MAIN SIMULATION LOOP ===
for month in range(1, 13):
    # Create time index with the current month
    times = time_range.map(lambda t: t.replace(month=month))

    if USE_REAL_WEATHER:
        try:
            weather, _, _, _ = iotools.get_pvgis_tmy(loc.latitude, loc.longitude, map_variables=True)
            weather = weather.loc[times]
        except Exception:
            weather = loc.get_clearsky(times)
    else:
        weather = loc.get_clearsky(times)

    mc.run_model(weather)
    total_dc_output = sum(mc.results.dc)

    month_name = calendar.month_name[month]
    results_raw[month_name] = total_dc_output.values

    energy_kwh = total_dc_output.sum() * (pd.Timedelta(TIME_STEP).total_seconds() / 3600)
    monthly_energy_kwh[month_name] = energy_kwh

# === BATTERY SIMULATION ===
results_battery = results_raw.copy()
if SIMULATE_BATTERY:
    for month in results_raw.columns:
        soc = 0.0
        adjusted_output = []
        for power in results_raw[month]:
            power_kw = power
            energy = power_kw * (pd.Timedelta(TIME_STEP).total_seconds() / 3600)

            if energy > 0:
                excess_energy = max(0, energy - 0.5)
                charge = min(excess_energy * BATTERY_CHARGE_EFFICIENCY, BATTERY_CAPACITY_KWH - soc)
                soc += charge
                net_energy = energy - charge
            else:
                net_energy = energy

            if net_energy < 0.5:
                needed = 0.5 - net_energy
                discharge = min(needed / BATTERY_DISCHARGE_EFFICIENCY, soc)
                soc -= discharge
                net_energy += discharge * BATTERY_DISCHARGE_EFFICIENCY

            adjusted_output.append(net_energy / (pd.Timedelta(TIME_STEP).total_seconds() / 3600))

        results_battery[month] = adjusted_output
else:
    results_battery = None

# === SMART GRID SIMULATION ===
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

# === PLOTTING ===
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
    ax.set_title(f'{title_prefix} - Hourly Energy Production for One Day in Each Month')
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
    ax.set_title(f'{title_prefix} - Normalized Hourly Energy Production for One Day in Each Month')
    ax.legend(title="Month", loc='upper left', bbox_to_anchor=(1, 1))
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.tight_layout()
    plt.show()

# Plot raw output (no battery or grid)
plot_monthly_profiles(results_raw, "Raw PV System Output")
plot_normalized_profiles(results_raw, "Raw PV System Output")

# Plot battery results if enabled
if SIMULATE_BATTERY and results_battery is not None:
    plot_monthly_profiles(results_battery, "With Battery Simulation")
    plot_normalized_profiles(results_battery, "With Battery Simulation")

# Plot smart grid results if enabled
if SIMULATE_SMART_GRID and results_smart_grid is not None:
    plot_monthly_profiles(results_smart_grid, "With Battery + Smart Grid Simulation")
    plot_normalized_profiles(results_smart_grid, "With Battery + Smart Grid Simulation")

# Additional energy summary
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
