# 🌞 Solar Tower Simulation Web Tool

This project is an interactive simulation tool for a **Vertical Solar Tower System**. It allows users to simulate photovoltaic (PV) energy output using real weather data, with options for battery storage and smart grid support. Built in Python using [pvlib](https://pvlib-python.readthedocs.io/), [Streamlit](https://streamlit.io), and optionally hosted on Streamlit Cloud or self-hosted.

---

## 📌 Features

* **Approximate User Location** based on IP (for Streamlit-hosted version).
* **Primary PV Simulation** using real PVGIS weather data.
* **Battery Simulation** with custom efficiency and capacity.
* **Smart Grid Support** to augment battery and handle power deficit.
* **Interactive Plots** for monthly profiles (with normalized and absolute power).
* **Monthly + Annual Energy Reports**.
* **"Update Simulation" Button** to prevent running simulations on every parameter change.
* Optional email capture before running battery simulation.

---

## 💻 Live Demo (Streamlit Hosted)

If deployed on Streamlit Cloud:

```
https://YOUR-STREAMLIT-USERNAME.streamlit.app/
```

Embed in your website using an `<iframe>`:

```html
<iframe src="https://YOUR-STREAMLIT-USERNAME.streamlit.app/" width="100%" height="900" frameborder="0"></iframe>
```

---

## ⚙️ Parameters & Workflow

* **Step 1**: User opens your website and clicks “Wake and Open” button → loads app.
* **Step 2**: App auto-detects approximate location via IP (if available).
* **Step 3**: User can adjust parameters (e.g., battery size, grid support).
* **Step 4**: User clicks **"Update Simulation"** to run simulation.
* **Step 5** *(optional)*: On “Simulate Battery” button click, an email prompt is shown.
* **Step 6**: Battery + smart grid simulation is performed and plotted.

---

## 🧱 Project Structure

```
├── app.py                # Main Streamlit application
├── simulation.py         # Core simulation logic using pvlib
├── utils.py              # Optional helper functions (location, plotting, etc.)
├── README.md             # This file
├── requirements.txt      # Python dependencies
```

---

## 🚀 Getting Started Locally

1. **Clone the repository**

```bash
git clone https://github.com/YOUR-USERNAME/solar-tower-sim.git
cd solar-tower-sim
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Run the app**

```bash
streamlit run app.py
```

---

## 🌍 Deployment Options

### ✅ 1. Streamlit Cloud (Recommended)

1. Push code to a GitHub repo.
2. Go to [Streamlit Cloud](https://streamlit.io/cloud).
3. Connect your GitHub account and deploy the repo.
4. Set up secrets if using email or API services.

### 💠 2. Self-host (on your server or VPS)

1. Install Python and required libraries.
2. Serve app using `streamlit run app.py`.
3. Use a reverse proxy (e.g., Nginx) for HTTPS.
4. Embed via iframe into your website.

---

## 🏦 Requirements

* `pvlib`
* `pandas`
* `numpy`
* `matplotlib`
* `streamlit`
* `requests` *(if IP-based geolocation is used)*

Install via:

```bash
pip install -r requirements.txt
```

---

## 📧 Contact / Contributions

Feel free to contribute or customize the tool for other PV technologies.
If you'd like to collaborate or need a customized simulation, reach out!

---

## 📜 License

MIT License
