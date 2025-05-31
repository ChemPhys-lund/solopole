import numpy as np
import matplotlib.pyplot as plt
from pvlib import pvsystem, modelchain, location, iotools
import pandas as pd
import calendar
import streamlit as st

# ------------------------------
# 🧩 Feature Toggles (controlled via UI)
# ------------------------------
st.set_page_config(layout="wide")
st.title("🗼 Vertical Solar Tower Simulator")

# Session state initialization
if 'raw_results' not in st.session_state:
    st.session_state.raw_results = None
    st.session_state.monthly_energy_kwh = None
    st.session_state.battery_results = None
    st.session_state.smart_grid_results = None

# ------------------------------
# 🌍 Location Input
# ------------------------------
st.sidebar.header("📍 Location")
latitude = st.sidebar.number_input("Latitude", value=40.0)
longitude = st.sidebar.number_input("Longitude", value=-80.0)

# ------------------------------
# ⚙️ Simulation Toggles
# ------------------------------
simulate_battery = st.sidebar.checkbox("Simulate Battery", value=False)
simulate_smart_grid = st.sidebar.checkbox("Simulate Smart Grid", value=False)

battery_capacity_kwh = 10.0  # fixed for now
grid_support_limit_kw = 2.0  # fixed for now

# ------------------------------
# 🔁 Update Button
# ------------------------------
update_sim = st.sidebar.button("Update Simulation")

# ------------------------------
# ⚙️ Helper Simulation Functions
# ------------------------------
def run_raw_simulation(lat, lon):
    loc = location.Location(latitude=lat, longitude=lon)
    tower_diameter = 0.6
    tower_height = 12
    panel_width = 0.3
    panel_height = 1.0
    power_density = 175

    num_panels_circumference = int(np.ceil((np.pi * tower_diameter) / panel_width))
    num_panels_height = int(tower_height / panel_height)

    panel_area_total = num_panels_circumference * num_panels_height * panel_width * panel_height
    total_dc_power_kw = (panel_area_total * power_density) / 1000
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
        ) for az in panel_orientations
    ]

    system = pvsystem.PVSystem(
        arrays=arrays,
        inverter_parameters=dict(pdc0=total_dc_power_kw)
    )

    mc = modelchain.ModelChain(system, loc, aoi_model='physical', spectral_model='no_loss')

    reference_date = '2019-01-01'
    time_range = pd.date_range(f'{reference_date} 05:00', f'{reference_date} 20:00', freq='1h', tz='Etc/GMT+5')
    times_local = time_range.tz_convert(loc.tz)
    time_of_day = times_local.strftime('%H:%M')
    time_of_day_shifted = (times_local + pd.Timedelta(hours=-5)).strftime('%H:%M')

    results_raw = pd.DataFrame(index=time_of_day)
    monthly_energy_kwh = {}

    weather, _, _, _ = iotools.get_pvgis_tmy(lat, lon, map_variables=True)

    for month in range(1, 13):
        times = time_range.map(lambda t: t.replace(month=month))
        try:
            weather_month = weather.loc[times]
        except:
            weather_month = loc.get_clearsky(times)

        mc.run_model(weather_month)
        total_dc_output = sum(mc.results.dc)

        month_name = calendar.month_name[month]
        results_raw[month_name] = total_dc_output.values
        energy_kwh = total_dc_output.sum() #* 0.5
        monthly_energy_kwh[month_name] = energy_kwh

    return results_raw, monthly_energy_kwh, time_of_day_shifted

def run_battery_simulation(raw_df):
    results_battery = raw_df.copy()
    battery_capacity = battery_capacity_kwh
    charge_eff = 0.95
    discharge_eff = 0.95

    for month in results_battery.columns:
        soc = 0.0
        adjusted_output = []
        for power in results_battery[month]:
            energy = power * 0.5
            excess = max(0, energy - 0.5)
            charge = min(excess * charge_eff, battery_capacity - soc)
            soc += charge
            net_energy = energy - charge

            if net_energy < 0.5:
                needed = 0.5 - net_energy
                discharge = min(needed / discharge_eff, soc)
                soc -= discharge
                net_energy += discharge * discharge_eff

            adjusted_output.append(net_energy / 0.5)

        results_battery[month] = adjusted_output

    return results_battery

def run_smart_grid_simulation(battery_df):
    results_grid = battery_df.copy()
    for month in results_grid.columns:
        results_grid[month] = [min(1.0, val) + min(grid_support_limit_kw, max(0.0, 1.0 - val)) if val < 1.0 else val for val in results_grid[month]]
    return results_grid

# ------------------------------
# 🚀 Simulation Trigger
# ------------------------------
if st.session_state.raw_results is None or update_sim:
    st.session_state.raw_results, st.session_state.monthly_energy_kwh, st.session_state.time_labels = run_raw_simulation(latitude, longitude)
    st.session_state.battery_results = None
    st.session_state.smart_grid_results = None

if simulate_battery and st.session_state.battery_results is None:
    st.session_state.battery_results = run_battery_simulation(st.session_state.raw_results)

if simulate_smart_grid and st.session_state.smart_grid_results is None:
    st.session_state.smart_grid_results = run_smart_grid_simulation(
        st.session_state.battery_results if st.session_state.battery_results is not None else st.session_state.raw_results
    )

# ------------------------------
# 📊 Plotting Section
# ------------------------------
def plot_profiles(df, time_labels, title):
    import matplotlib.pyplot as plt
    import seaborn as sns
    import io

    fig, ax = plt.subplots(figsize=(12, 6))
    markers = ['o', 's', 'D', '^', 'v', '<', '>', 'p', '*', 'h', 'H', 'X']
    colors = plt.cm.get_cmap('tab10', 12)

    for i, month in enumerate(df.columns):
        ax.plot(time_labels, df[month], label=month, color=colors(i), marker=markers[i], linestyle='-')

    ax.set_xlabel("Time of Day")
    ax.set_ylabel("System Output (kW)")
    ax.set_title(title)
    ax.legend(title="Month", loc='upper left', bbox_to_anchor=(1, 1))
    plt.xticks(rotation=45)
    plt.grid(True)
    st.pyplot(fig)

st.subheader("🔋 Raw PV Output")
plot_profiles(st.session_state.raw_results, st.session_state.time_labels, "Raw PV System Output")

if simulate_battery and st.session_state.battery_results is not None:
    st.subheader("🔋 With Battery Simulation")
    plot_profiles(st.session_state.battery_results, st.session_state.time_labels, "Battery-Adjusted PV Output")

if simulate_smart_grid and st.session_state.smart_grid_results is not None:
    st.subheader("🧠 Battery + Smart Grid")
    plot_profiles(st.session_state.smart_grid_results, st.session_state.time_labels, "PV Output with Smart Grid")

# ------------------------------
# 📊 Energy Summary
# ------------------------------
st.subheader("📅 Monthly Energy Report (kWh)")
fig, ax = plt.subplots(figsize=(10, 4))
ax.bar(st.session_state.monthly_energy_kwh.keys(), st.session_state.monthly_energy_kwh.values(), color='skyblue')
ax.set_ylabel("kWh")
ax.set_title("Monthly Energy Output")
plt.xticks(rotation=45)
st.pyplot(fig)

st.markdown(f"**🔆 Total Annual Energy Output:** `{sum(st.session_state.monthly_energy_kwh.values()):.2f} kWh`")
