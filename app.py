
import streamlit as st
import pvlib
from pvlib.location import Location
from pvlib.pvsystem import PVSystem
from pvlib.modelchain import ModelChain
from pvlib.iotools import get_pvgis_tmy
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

st.title("Vertical Solar Tower Energy Simulator")

# --- User Inputs ---
st.sidebar.header("Tower Configuration")
height_m = st.sidebar.slider("Tower Height (m)", 2, 12, 6)
diameter_m = st.sidebar.slider("Tower Diameter (m)", 0.3, 1.0, 0.6)
sunlit_fraction = st.sidebar.slider("Sunlit Fraction", 0.5, 1.0, 0.7)
cigs_efficiency = st.sidebar.slider("Panel Efficiency (CIGS)", 0.10, 0.20, 0.15)

st.sidebar.header("Location Settings")
latitude = st.sidebar.number_input("Latitude", value=28.6139)
longitude = st.sidebar.number_input("Longitude", value=77.2090)
tz = 'Asia/Kolkata'

# --- Derived Area & Power ---
circumference = np.pi * diameter_m
usable_area_m2 = height_m * circumference * sunlit_fraction
total_dc_power_watts = usable_area_m2 * 1000 * cigs_efficiency
st.write(f"Estimated DC Capacity: **{total_dc_power_watts:.1f} W**")

# --- Weather Data ---
st.write("Fetching typical meteorological year data from PVGIS...")
site = Location(latitude, longitude, tz)
tmy_data, meta = get_pvgis_tmy(latitude, longitude, map_variables=True)
weather = tmy_data.rename(columns={
    'temp_air': 'temp_air',
    'ghi': 'ghi',
    'dni': 'dni',
    'dhi': 'dhi',
    'wind_speed': 'wind_speed'
})
weather.index = weather.index.tz_convert(tz)

# --- PV System Setup ---
temperature_model_parameters = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS['sapm']['open_rack_glass_glass']
system = PVSystem(
    surface_tilt=90,
    surface_azimuth=180,
    module_parameters={'pdc0': total_dc_power_watts, 'gamma_pdc': -0.0035},
    temperature_model_parameters=temperature_model_parameters,
    modules_per_string=1,
    strings_per_inverter=1
)

mc = ModelChain(system, site, orientation_strategy=None)
mc.run_model(weather)
ac_power = mc.results.ac

# --- Energy Calculation ---
shading_loss_factor = 0.85
battery_efficiency = 0.90
charge_controller_efficiency = 0.97
overall_efficiency = shading_loss_factor * battery_efficiency * charge_controller_efficiency

daily_energy = ac_power.resample('D').sum() / 1000
net_daily_energy = daily_energy * overall_efficiency

monthly_energy = net_daily_energy.resample('M').sum()
peak_power = ac_power.max()

# --- Plot Monthly Energy ---
st.subheader("Monthly Net Energy Output (kWh)")
st.bar_chart(monthly_energy)

st.subheader("Key Results")
st.write(f"**Peak Instantaneous AC Power:** {peak_power:.2f} W")
st.write(f"**Average Daily Energy (Net):** {net_daily_energy.mean():.2f} kWh")
