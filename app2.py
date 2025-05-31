import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import calendar
from pvlib import pvsystem, modelchain, location, iotools

# ===============================
# Global parameters (easy to edit)
# ===============================

# Location defaults
DEFAULT_LATITUDE = 40.0
DEFAULT_LONGITUDE = -80.0

# Tower specs
TOWER_DIAMETER = 0.6  # meters
TOWER_HEIGHT = 12.0  # meters

# Panel specs
PANEL_WIDTH = 0.1  # meters
PANEL_HEIGHT = 1.0  # meters
POWER_DENSITY = 175  # W/m²

# Battery
BATTERY_CAPACITY_KWH = 10.0
BATTERY_CHARGE_EFFICIENCY = 0.95
BATTERY_DISCHARGE_EFFICIENCY = 0.95

# Grid
GRID_SUPPORT_LIMIT_KW = 2.0

# Simulation time settings
TIMEZONE = 'Etc/GMT+5'
FREQ = '30min'  # 30 minute frequency for simulation steps

# ======================================
# Helper functions for simulation + plots
# ======================================

def create_location(lat, lon):
    return location.Location(latitude=lat, longitude=lon, tz=TIMEZONE)

def create_arrays(tower_diameter, tower_height, panel_width, panel_height, power_density):
    num_panels_circ = int(np.ceil(np.pi * tower_diameter / panel_width))
    num_panels_height = int(tower_height / panel_height)
    panel_area_total = num_panels_circ * num_panels_height * panel_width * panel_height  # m²
    total_dc_power_kw = (panel_area_total * power_density) / 1000  # kW

    panel_orientations = np.linspace(0, 360, num_panels_circ, endpoint=False)

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

    return system, total_dc_power_kw

def generate_time_range(reference_date, freq, tz):
    # Full day from 00:00 to 23:30 local time
    time_range_local = pd.date_range(f'{reference_date} 00:00', f'{reference_date} 23:30', freq=freq, tz=tz)
    return time_range_local

def get_weather_data(loc, times, use_real_weather=True):
    if use_real_weather:
        try:
            weather, metadata_list, metadata_dict, _ = iotools.get_pvgis_tmy(loc.latitude, loc.longitude, map_variables=True)
            weather = weather.loc[times]
            return weather
        except Exception as e:
            st.warning(f"Real weather data fetch failed, using clearsky: {e}")
            return loc.get_clearsky(times)
    else:
        return loc.get_clearsky(times)

def run_pv_simulation(system, mc, loc, time_range, use_real_weather):
    results = pd.DataFrame()
    monthly_energy_kwh = {}

    for month in range(1, 13):
        # Replace month in time_range
        times = time_range.map(lambda t: t.replace(month=month))

        weather = get_weather_data(loc, times, use_real_weather)
        mc.run_model(weather)
        total_dc_output = sum(mc.results.dc)

        month_name = calendar.month_name[month]
        results[month_name] = total_dc_output.values

        # Calculate monthly energy kWh
        step_hours = pd.Timedelta(mc.results.index.freq).total_seconds() / 3600
        energy_kwh = total_dc_output.sum() * step_hours
        monthly_energy_kwh[month_name] = energy_kwh

    results.index = time_range.strftime('%H:%M')
    return results, monthly_energy_kwh

def simulate_battery(raw_output, capacity_kwh, charge_eff, discharge_eff, step_hours=0.5):
    results_battery = raw_output.copy()
    for month in raw_output.columns:
        soc = 0.0
        adjusted_output = []
        for power in raw_output[month]:
            energy = power * step_hours
            if energy > 0:
                excess_energy = max(0, energy - 0.5)  # constant load 0.5 kWh assumed
                charge = min(excess_energy * charge_eff, capacity_kwh - soc)
                soc += charge
                net_energy = energy - charge
            else:
                net_energy = energy

            if net_energy < 0.5:
                needed = 0.5 - net_energy
                discharge = min(needed / discharge_eff, soc)
                soc -= discharge
                net_energy += discharge * discharge_eff

            adjusted_output.append(net_energy / step_hours)
        results_battery[month] = adjusted_output
    return results_battery

def simulate_smart_grid(battery_output, grid_limit_kw):
    results_grid = battery_output.copy()
    for month in battery_output.columns:
        adjusted_output = []
        for power_kw in battery_output[month]:
            load_kw = 1.0
            if power_kw < load_kw:
                support = min(grid_limit_kw, load_kw - power_kw)
                adjusted_output.append(power_kw + support)
            else:
                adjusted_output.append(power_kw)
        results_grid[month] = adjusted_output
    return results_grid

def plot_monthly_profiles(df, title_prefix):
    markers = ['o', 's', 'D', '^', 'v', '<', '>', 'p', '*', 'h', 'H', 'X']
    colors = plt.cm.get_cmap('tab10', 12)

    fig, ax = plt.subplots(figsize=(12, 8))
    for i, month in enumerate(range(1, 13)):
        month_name = calendar.month_name[month]
        ax.plot(df.index, df[month_name],
                marker=markers[i], color=colors(i), label=month_name, linestyle='-')
    ax.set_xlabel('Time of Day')
    ax.set_ylabel('Total System Output (kW)')
    ax.set_title(f'{title_prefix} - Hourly Energy Production for One Day in Each Month')
    ax.legend(title="Month", loc='upper left', bbox_to_anchor=(1, 1))
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.tight_layout()
    st.pyplot(fig)

def plot_normalized_profiles(df, title_prefix):
    markers = ['o', 's', 'D', '^', 'v', '<', '>', 'p', '*', 'h', 'H', 'X']
    colors = plt.cm.get_cmap('tab10', 12)

    fig, ax = plt.subplots(figsize=(12, 8))
    for i, month in enumerate(range(1, 13)):
        month_name = calendar.month_name[month]
        normalized = df[month_name] / df[month_name].max()
        ax.plot(df.index, normalized,
                marker=markers[i], color=colors(i), label=month_name, linestyle='-')
    ax.set_xlabel('Time of Day')
    ax.set_ylabel('Normalized System Output')
    ax.set_title(f'{title_prefix} - Normalized Hourly Energy Production for One Day in Each Month')
    ax.legend(title="Month", loc='upper left', bbox_to_anchor=(1, 1))
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.tight_layout()
    st.pyplot(fig)

# ======================
# Streamlit app starts here
# ======================

st.title("Solar Tower Energy Simulation")

# Sidebar inputs
st.sidebar.header("Simulation Settings")
latitude = st.sidebar.number_input("Latitude", value=DEFAULT_LATITUDE, format="%.6f")
longitude = st.sidebar.number_input("Longitude", value=DEFAULT_LONGITUDE, format="%.6f")
use_real_weather = st.sidebar.checkbox("Use Real Weather Data (PVGIS TMY)", value=True)
simulate_battery_flag = st.sidebar.checkbox("Simulate Battery", value=False)
simulate_grid_flag = st.sidebar.checkbox("Simulate Smart Grid", value=False)

# Buttons
run_raw_sim = st.sidebar.button("Run Raw PV Output Simulation")
run_battery_sim = st.sidebar.button("Run Battery + Smart Grid Simulation")

# Create Location and System upfront
loc = create_location(latitude, longitude)
system, total_dc_power_kw = create_arrays(TOWER_DIAMETER, TOWER_HEIGHT, PANEL_WIDTH, PANEL_HEIGHT, POWER_DENSITY)
mc = modelchain.ModelChain(system, loc, aoi_model='physical', spectral_model='no_loss')

reference_date = '2019-01-01'
time_range = generate_time_range(reference_date, FREQ, loc.tz)

# Store simulation results in session state to avoid recomputation
if 'results_raw' not in st.session_state:
    st.session_state['results_raw'], st.session_state['monthly_energy_raw'] = run_pv_simulation(system, mc, loc, time_range, use_real_weather)
if 'results_battery' not in st.session_state:
    st.session_state['results_battery'] = None
if 'results_grid' not in st.session_state:
    st.session_state['results_grid'] = None

# Run raw simulation if button pressed
if run_raw_sim:
    st.session_state['results_raw'], st.session_state['monthly_energy_raw'] = run_pv_simulation(system, mc, loc, time_range, use_real_weather)
    st.success("Raw PV Output Simulation completed.")

# Display raw simulation results
st.subheader("Raw PV Output Simulation Results")
plot_monthly_profiles(st.session_state['results_raw'], "Raw PV Output")
plot_normalized_profiles(st.session_state['results_raw'], "Raw PV Output")

# Show monthly and annual summaries
st.markdown("### Monthly Energy Production (kWh)")
monthly_energy_df = pd.DataFrame.from_dict(st.session_state['monthly_energy_raw'], orient='index', columns=['Energy (kWh)'])
monthly_energy_df.index.name = "Month"
st.dataframe(monthly_energy_df)
annual_energy = monthly_energy_df['Energy (kWh)'].sum()
st.markdown(f"**Annual Energy Production:** {annual_energy:.2f} kWh")

# Battery + Grid simulation
if simulate_battery_flag:
    if run_battery_sim:
        st.session_state['results_battery'] = simulate_battery(st.session_state['results_raw'], BATTERY_CAPACITY_KWH, BATTERY_CHARGE_EFFICIENCY, BATTERY_DISCHARGE_EFFICIENCY)
        st.success("Battery Simulation completed.")
    if st.session_state['results_battery'] is not None:
        st.subheader("Battery Simulation Results")
        plot_monthly_profiles(st.session_state['results_battery'], "Battery Output")
        plot_normalized_profiles(st.session_state['results_battery'], "Battery Output")

if simulate_grid_flag and st.session_state.get('results_battery') is not None:
    if run_battery_sim:
        st.session_state['results_grid'] = simulate_smart_grid(st.session_state['results_battery'], GRID_SUPPORT_LIMIT_KW)
        st.success("Smart Grid Simulation completed.")
    if st.session_state['results_grid'] is not None:
        st.subheader("Smart Grid Simulation Results")
        plot_monthly_profiles(st.session_state['results_grid'], "Smart Grid Output")
        plot_normalized_profiles(st.session_state['results_grid'], "Smart Grid Output")
