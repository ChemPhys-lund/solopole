import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Solar panel specifications
panel_area = 6 * np.pi * 0.6 * 0.7  # Tower's panel area in m² (height * circumference * sunlit fraction)
panel_efficiency = 0.15  # 15% efficiency

# Function to calculate daily energy generation based on irradiance and panel specifications
def calculate_daily_energy(irradiance=5.0):
    # Default irradiance value in kWh/m²/day (example: 5 kWh/m²/day)
    daily_energy = irradiance * panel_area * panel_efficiency
    return daily_energy

# Streamlit app
st.title("Solar Power Generation Estimator")

# Input for irradiance (user can modify if they want)
irradiance = st.slider('Select average daily irradiance (kWh/m²/day)', min_value=2.0, max_value=7.0, value=5.0, step=0.1)

# Calculate daily energy generation
daily_energy = calculate_daily_energy(irradiance)
st.write(f"Estimated Daily Energy Output: {daily_energy:.2f} kWh")

# Monthly energy generation estimation
monthly_energy = daily_energy * 30  # Assuming 30 days in a month
st.write(f"Estimated Monthly Energy Output: {monthly_energy:.2f} kWh")

# Plot monthly power generation
st.subheader("Monthly Energy Generation")
months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
monthly_generation = [monthly_energy for _ in months]

fig, ax = plt.subplots()
ax.bar(months, monthly_generation, color='skyblue')
ax.set_xlabel('Month')
ax.set_ylabel('Energy (kWh)')
ax.set_title('Estimated Monthly Energy Generation')
st.pyplot(fig)

# Peak Power Generation
peak_power = daily_energy * panel_efficiency  # Assuming peak power is based on daily irradiance
st.write(f"Estimated Peak Power Generation: {peak_power:.2f} kW")

