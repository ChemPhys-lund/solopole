import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import calendar
from pvlib import pvsystem, modelchain, location, iotools

# -------------------------
# ⚙️ Helper Functions
# -------------------------

def run_simulation(latitude, longitude, battery_enabled, smart_grid_enabled):
    tower_diameter = 0.6
    tower_height = 12
    panel_width = 0.1
    panel_height = 1.0
    power_density = 175  # W/m²
    
    num_panels_circumference = int(np.ceil((np.pi * tower_diameter) / panel_width))
    num_panels_height = int(tower_height / panel_height)

    panel_area_total = num_panels_circumference * num_panels_height * panel_width * panel_height
    total_dc_power_kw = (panel_area_total * power_density) / 1000

    panel_orientations = np.linspace(0, 360, num_panels_circumference, endpoint=False)

    loc = location.Location(latitude=latitude, longitude=longitude)

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
    time_range = pd.date_range(f'{reference_date} 05:00', f'{reference_date} 20:00', freq='0.5h', tz='Etc/GMT+5')
    times_local = time_range.tz_convert(loc.tz)
    time_of_day = times_local.strftime('%H:%M')
    time_of_day_shifted = (times_local + pd.Timedelta(hours=-5)).strftime('%H:%M')

    results_raw = pd.DataFrame(index=time_of_day)
    monthly_energy_kwh = {}

    for month in range(1, 13):
        times = time_range.map(lambda t: t.replace(month=month))

        try:
            weather, _, _, _ = iotools.get_pvgis_tmy(loc.latitude, loc.longitude, map_variables=True)
            weather = weather.loc[times]
        except:
            weather = loc.get_clearsky(times)

        mc.run_model(weather)
        total_dc_output = sum(mc.results.dc)
        month_name = calendar.month_name[month]
        results_raw[month_name] = total_dc_output.values
        energy_kwh = total_dc_output.sum() * 0.5
        monthly_energy_kwh[month_name] = energy_kwh

    results_battery = results_raw.copy()
    if battery_enabled:
        for month in results_raw.columns:
            soc = 0.0
            adjusted_output = []
            for power in results_raw[month]:
                energy = power * 0.5
                excess = max(0, energy - 0.5)
                charge = min(excess * 0.95, 10.0 - soc)
                soc += charge
                net_energy = energy - charge
                if net_energy < 0.5:
                    needed = 0.5 - net_energy
                    discharge = min(needed / 0.95, soc)
                    soc -= discharge
                    net_energy += discharge * 0.95
                adjusted_output.append(net_energy / 0.5)
            results_battery[month] = adjusted_output

    results_smart_grid = results_battery.copy() if battery_enabled else results_raw.copy()
    if smart_grid_enabled:
        for month in results_smart_grid.columns:
            adjusted_output = []
            for power_kw in results_smart_grid[month]:
                if power_kw < 1.0:
                    support = min(2.0, 1.0 - power_kw)
                    adjusted_output.append(power_kw + support)
                else:
                    adjusted_output.append(power_kw)
            results_smart_grid[month] = adjusted_output

    return time_of_day_shifted, results_raw, results_battery, results_smart_grid, monthly_energy_kwh


def plot_monthly_profiles(df, time_labels, title):
    import matplotlib.pyplot as plt
    import matplotlib
    fig, ax = plt.subplots(figsize=(12, 8))
    colors = plt.cm.get_cmap('tab10', 12)
    markers = ['o', 's', 'D', '^', 'v', '<', '>', 'p', '*', 'h', 'H', 'X']
    for i, month in enumerate(df.columns):
        ax.plot(time_labels, df[month], marker=markers[i], color=colors(i), label=month, linestyle='-')
    ax.set_xlabel('Time of Day')
    ax.set_ylabel('Power Output (kW)')
    ax.set_title(title)
    ax.legend(title="Month", loc='upper left', bbox_to_anchor=(1, 1))
    ax.grid(True)
    plt.xticks(rotation=45)
    st.pyplot(fig)


# -------------------------
# 🌐 Streamlit App UI
# -------------------------

st.set_page_config(layout="wide")
st.title("☀️ Vertical Solar Tower Simulation")

st.markdown("""
This tool simulates hourly solar energy output for a vertical solar tower.
""")

with st.form(key="simulation_form"):
    latitude = st.number_input("Latitude", value=40.0)
    longitude = st.number_input("Longitude", value=-80.0)
    battery_enabled = st.checkbox("Enable Battery Simulation")
    smart_grid_enabled = st.checkbox("Enable Smart Grid Support")
    submit = st.form_submit_button("Update Simulation")

if submit:
    with st.spinner("Running simulation..."):
        time_labels, raw, battery, grid, monthly_kwh = run_simulation(latitude, longitude, battery_enabled, smart_grid_enabled)

        st.subheader("📊 Monthly Hourly Profiles")
        plot_monthly_profiles(raw, time_labels, "Raw PV Output")

        if battery_enabled:
            plot_monthly_profiles(battery, time_labels, "Battery Simulation Output")

        if smart_grid_enabled:
            plot_monthly_profiles(grid, time_labels, "Battery + Smart Grid Output")

        st.subheader("🔋 Monthly Energy Summary (kWh)")
        df_energy = pd.DataFrame.from_dict(monthly_kwh, orient='index', columns=['Energy (kWh)'])
        st.bar_chart(df_energy)

        st.success(f"✅ Total Annual Energy: {sum(monthly_kwh.values()):.2f} kWh")

