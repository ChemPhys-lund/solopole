import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import calendar
from pvlib import pvsystem, modelchain, location, iotools

# ------------------------------
# 🧰 Sidebar: User Input
# ------------------------------
st.set_page_config(layout="wide")
st.title("🌞 Vertical Solar Tower Energy Simulator")

st.sidebar.header("Simulation Parameters")
latitude = st.sidebar.number_input("Latitude", value=40.0, format="%f")
longitude = st.sidebar.number_input("Longitude", value=-80.0, format="%f")
battery_enabled = st.sidebar.checkbox("Simulate Battery", value=False)
battery_capacity_kwh = st.sidebar.slider("Battery Capacity (kWh)", 0.0, 50.0, 10.0)
grid_enabled = st.sidebar.checkbox("Simulate Smart Grid", value=False)
grid_limit_kw = st.sidebar.slider("Grid Support Limit (kW)", 0.0, 5.0, 2.0)

# ------------------------------
# 🌳 System Specs
# ------------------------------
tower_diameter = 0.6  # meters
tower_height = 12  # meters
panel_width = 0.1  # meters
panel_height = 1.0  # meters
power_density = 175  # W/m^2

num_panels_circ = int(np.ceil((np.pi * tower_diameter) / panel_width))
num_panels_height = int(tower_height / panel_height)
panel_area_total = num_panels_circ * num_panels_height * panel_width * panel_height  # m^2
total_dc_power_kw = (panel_area_total * power_density) / 1000  # kW

orientations = np.linspace(0, 360, num_panels_circ, endpoint=False)
loc = location.Location(latitude=latitude, longitude=longitude)

array_kwargs = dict(
    module_parameters=dict(pdc0=1, gamma_pdc=-0.004),
    temperature_model_parameters=dict(a=-3.56, b=-0.075, deltaT=3)
)

arrays = [
    pvsystem.Array(mount=pvsystem.FixedMount(90, az), name=f"Array {az:.1f}°", **array_kwargs)
    for az in orientations
]

system = pvsystem.PVSystem(
    arrays=arrays,
    inverter_parameters=dict(pdc0=total_dc_power_kw)
)
mc = modelchain.ModelChain(system, loc, aoi_model='physical', spectral_model='no_loss')

# ------------------------------
# 🔄 Time Series Setup
# ------------------------------
reference_date = '2019-01-01'
time_range = pd.date_range(f'{reference_date} 05:00', f'{reference_date} 20:00', freq='0.5h', tz='Etc/GMT+5')
times_local = time_range.tz_convert(loc.tz)
time_of_day = times_local.strftime('%H:%M')
time_of_day_shifted = (times_local + pd.Timedelta(hours=0)).strftime('%H:%M')

# ------------------------------
# 📊 Simulation
# ------------------------------
results_raw = pd.DataFrame(index=time_of_day)
monthly_energy_kwh = {}

for month in range(1, 13):
    times = time_range.map(lambda t: t.replace(month=month))
    try:
        weather, _, _, _ = iotools.get_pvgis_tmy(latitude, longitude, map_variables=True)
        weather = weather.loc[times]
    except:
        weather = loc.get_clearsky(times)

    mc.run_model(weather)
    total_dc_output = sum(mc.results.dc)
    month_name = calendar.month_name[month]
    results_raw[month_name] = total_dc_output.values
    energy_kwh = total_dc_output.sum() * 0.5  # 0.5 hour steps
    monthly_energy_kwh[month_name] = energy_kwh

# ------------------------------
# 🔋 Battery Simulation
# ------------------------------
results_battery = results_raw.copy()
if battery_enabled:
    for month in results_raw.columns:
        soc = 0.0
        adjusted = []
        for power in results_raw[month]:
            energy = power * 0.5
            excess = max(0, energy - 0.5)
            charge = min(excess * 0.95, battery_capacity_kwh - soc)
            soc += charge
            net = energy - charge
            if net < 0.5:
                needed = 0.5 - net
                discharge = min(needed / 0.95, soc)
                soc -= discharge
                net += discharge * 0.95
            adjusted.append(net / 0.5)
        results_battery[month] = adjusted
else:
    results_battery = None

# ------------------------------
# 🚜 Smart Grid
# ------------------------------
results_smart_grid = results_battery.copy() if results_battery is not None else results_raw.copy()
if grid_enabled:
    for month in results_smart_grid.columns:
        adjusted = []
        for power_kw in results_smart_grid[month]:
            if power_kw < 1.0:
                support = min(grid_limit_kw, 1.0 - power_kw)
                adjusted.append(power_kw + support)
            else:
                adjusted.append(power_kw)
        results_smart_grid[month] = adjusted
else:
    results_smart_grid = None

# ------------------------------
# 📊 Plotting
# ------------------------------
def plot_profiles(df, title):
    st.subheader(title)
    fig, ax = plt.subplots(figsize=(10, 6))
    for i, month in enumerate(df.columns):
        ax.plot(time_of_day_shifted, df[month], label=month)
    ax.set_xlabel("Time of Day")
    ax.set_ylabel("Power Output (kW)")
    ax.legend()
    ax.grid(True)
    st.pyplot(fig)

def plot_energy_summary(energy_dict):
    st.subheader("Monthly Energy Production")
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(energy_dict.keys(), energy_dict.values(), color='skyblue')
    ax.set_ylabel("Energy (kWh)")
    ax.set_title("Monthly Energy Output")
    ax.tick_params(axis='x', rotation=45)
    st.pyplot(fig)
    total = sum(energy_dict.values())
    st.success(f"Total Annual Energy: {total:.2f} kWh")

# Show plots
plot_profiles(results_raw, "Raw PV Output")
if battery_enabled:
    plot_profiles(results_battery, "With Battery Simulation")
if grid_enabled:
    plot_profiles(results_smart_grid, "With Battery + Smart Grid")
plot_energy_summary(monthly_energy_kwh)
