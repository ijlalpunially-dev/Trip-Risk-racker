"""
Climate Change Tracker — Mountain Trip Risk Checker (Streamlit)

How to run:
1. Create a virtual environment (optional) and install requirements:
   pip install -r requirements.txt

2. Obtain an OpenWeatherMap API key (free tier):
   https://openweathermap.org/api

3. Set environment variables (or paste keys into the UI):
   - OPENWEATHER_API_KEY  : your OpenWeatherMap API key
   (Optional) you can leave blank and use demo data.

4. Run:
   streamlit run app.py

Notes:
- If you provide latitude & longitude, the app can optionally check elevation
  using a free elevation API (open-elevation). If elevation > 1000m we treat it
  as mountainous (you can override).
- The risk logic is simple and conservative: rain/snow/strong winds increase risk
  in mountainous areas. You can customize thresholds below.
"""

import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # loads .env if present

# -------------------------
# Config / thresholds
# -------------------------
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()

# Elevation threshold (meters) above which we label location as mountainous
ELEVATION_MOUNTAIN_THRESHOLD = 1000

# Wind (m/s) threshold for "strong wind"
WIND_STRONG_THRESHOLD = 10.0

# Rain or snow volume threshold (mm in last 1h) considered significant if API returns it
PRECIP_THRESHOLD_MM = 0.1

# -------------------------
# Helpers: External APIs
# -------------------------
def fetch_weather_by_coords(lat, lon, api_key):
    """
    Uses OpenWeatherMap current weather API. Returns dict or raises on failure.
    """
    base = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": "metric",
    }
    r = requests.get(base, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def fetch_weather_by_city(city_name, api_key):
    base = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city_name,
        "appid": api_key,
        "units": "metric",
    }
    r = requests.get(base, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def fetch_elevation(lat, lon):
    """
    Query a free elevation API. Returns elevation in meters or None on failure.
    Uses open-elevation (public).
    """
    try:
        url = "https://api.open-elevation.com/api/v1/lookup"
        params = {"locations": f"{lat},{lon}"}
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        if "results" in data and len(data["results"]) > 0:
            return data["results"][0].get("elevation")
    except Exception:
        return None
    return None

# -------------------------
# Risk logic
# -------------------------
def analyze_risk(weather_json, is_mountainous):
    """
    Very simple rule-based risk assessment for mountain trips.
    Returns dict: {risk_level, reasons(list), advice(list)}
    """
    reasons = []
    advice = []

    # Parse common fields with safe fallbacks
    weather_main = ""
    weather_desc = ""
    if "weather" in weather_json and len(weather_json["weather"]) > 0:
        weather_main = weather_json["weather"][0].get("main", "").lower()
        weather_desc = weather_json["weather"][0].get("description", "").lower()

    temp_c = weather_json.get("main", {}).get("temp")
    wind_speed = weather_json.get("wind", {}).get("speed", 0.0)  # m/s
    rain_1h = 0.0
    snow_1h = 0.0
    if "rain" in weather_json:
        rain_1h = weather_json["rain"].get("1h", 0.0)
    if "snow" in weather_json:
        snow_1h = weather_json["snow"].get("1h", 0.0)

    # Basic flags
    has_rain = ("rain" in weather_main) or (rain_1h >= PRECIP_THRESHOLD_MM) or ("shower" in weather_desc)
    has_snow = ("snow" in weather_main) or (snow_1h >= PRECIP_THRESHOLD_MM)
    is_windy = wind_speed >= WIND_STRONG_THRESHOLD
    is_cold = (temp_c is not None) and (temp_c <= 0)

    # Evaluate risk
    risk_score = 0
    # Mountainous multiplies risk
    if is_mountainous:
        risk_weight = 2.0
    else:
        risk_weight = 1.0

    if has_rain:
        reasons.append(f"Precipitation detected (rain ~ {rain_1h} mm in last hour).")
        risk_score += 2 * risk_weight
    if has_snow:
        reasons.append(f"Snow detected (snow ~ {snow_1h} mm in last hour).")
        risk_score += 3 * risk_weight
    if is_windy:
        reasons.append(f"Strong wind (~{wind_speed} m/s).")
        risk_score += 2 * risk_weight
    if is_cold:
        reasons.append(f"Low temperature ({temp_c} °C).")
        risk_score += 1.5 * risk_weight
    if "thunder" in weather_desc or "storm" in weather_desc:
        reasons.append(f"Thunderstorm / storm conditions reported: {weather_desc}.")
        risk_score += 3 * risk_weight
    if weather_main == "clear" and not (has_rain or has_snow or is_windy or is_cold):
        reasons.append("Clear conditions currently.")

    # Convert risk_score to category
    if risk_score >= 6:
        level = "High"
        advice = [
            "Avoid travel if possible — high risk conditions for mountain areas.",
            "Postpone the trip or choose a lower-altitude route.",
            "If travel is necessary, carry warm waterproof gear, inform someone, and have emergency kit."
        ]
    elif risk_score >= 2.5:
        level = "Medium"
        advice = [
            "Caution advised. Conditions may be risky, especially on exposed or steep terrain.",
            "Check local forecasts and consider delaying if the weather worsens.",
            "Bring waterproof layers, navigation, and an emergency plan."
        ]
    else:
        level = "Low"
        advice = [
            "Conditions appear OK for trips, but weather can change rapidly in mountains.",
            "Bring layers, sun protection, and check updates before leaving."
        ]

    # Add a note if not mountainous
    if not is_mountainous:
        reasons.insert(0, "Location is not identified as mountainous (lower elevation or user selected). Risk is assessed for non-mountain conditions.")
        # Slightly reduce severity if lowland
        if level == "High":
            level += " (mountain hazard less likely due to low elevation)"

    return {
        "level": level,
        "reasons": reasons,
        "advice": advice,
        "raw": {
            "temp_c": temp_c,
            "wind_speed": wind_speed,
            "rain_1h": rain_1h,
            "snow_1h": snow_1h,
            "weather_main": weather_main,
            "weather_desc": weather_desc,
        },
    }

# -------------------------
# Streamlit UI
# -------------------------
st.set_page_config(page_title="Climate Change Tracker — Mountain Trip Risk", layout="centered")

st.title("🌦️ Climate Change Tracker — Mountain Trip Risk Checker")
st.markdown(
    "This app evaluates current weather & elevation (optional) and gives a conservative *risk* assessment for mountain trips."
)

st.sidebar.header("Inputs / Settings")
use_demo = st.sidebar.checkbox("Use demo (no API key required)", value=False)

api_key_input = st.sidebar.text_input("OpenWeatherMap API key (leave blank to use .env)", value=OPENWEATHER_API_KEY if OPENWEATHER_API_KEY else "")

# Location input mode
loc_mode = st.sidebar.radio("Provide location by:", ("City name", "Latitude & Longitude"))

if loc_mode == "City name":
    city = st.text_input("City (e.g. 'Skardu, PK' or 'Kathmandu')", value="Skardu")
    lat = lon = None
else:
    col1, col2 = st.columns(2)
    with col1:
        lat = st.text_input("Latitude", value="35.2137")
    with col2:
        lon = st.text_input("Longitude", value="75.4460")
    city = None

auto_elev = st.sidebar.checkbox("Auto-detect elevation (requires lat/lon)", value=True)
force_mountain = st.sidebar.checkbox("Force mark as mountainous (override)", value=False)
elevation_override = None

st.markdown("---")
st.markdown("**How it works:** the app fetches current weather from OpenWeatherMap. If you provide lat/lon and enable auto elevation, it will query a public elevation API to decide if the place is mountainous (elevation > 1000 m).")

if use_demo:
    st.info("Demo mode: no external API calls. Using sample weather for demonstration.")
else:
    if not (api_key_input and api_key_input.strip()):
        st.warning("No OpenWeatherMap API key provided in the sidebar. You can either enter a key or enable Demo mode. Running without a key will fail to fetch live weather.")

# Run button
if st.button("Check risk now"):
    st.spinner("Fetching data...")
    try:
        # Decide which API key to use
        api_key = api_key_input.strip() if api_key_input.strip() else OPENWEATHER_API_KEY

        if use_demo:
            # Demo sample weather JSON (sunny mountain example)
            demo_weather = {
                "weather": [{"main": "Clear", "description": "clear sky"}],
                "main": {"temp": 4.5},
                "wind": {"speed": 3.2},
                "rain": {},
                "snow": {},
            }
            weather_json = demo_weather
            elevation = 3200  # sample mountain elevation
            is_mountainous = True
            st.success("Demo data loaded.")
        else:
            if loc_mode == "City name":
                if not city or not api_key:
                    st.error("City name provided but no API key available. Please add an API key or enable Demo mode.")
                    st.stop()
                weather_json = fetch_weather_by_city(city, api_key)
                # If city provided, no elevation auto-detect (unless user supply lat/lon separately). Offer manual elevation input.
                elevation = None
                is_mountainous = force_mountain or False
            else:
                # lat/lon mode
                if not lat or not lon:
                    st.error("Please provide both latitude and longitude.")
                    st.stop()
                try:
                    lat_f = float(lat)
                    lon_f = float(lon)
                except ValueError:
                    st.error("Latitude and Longitude must be numeric.")
                    st.stop()
                if not api_key:
                    st.error("No OpenWeatherMap API key available. Please enter one in the sidebar or enable Demo mode.")
                    st.stop()
                # fetch weather
                weather_json = fetch_weather_by_coords(lat_f, lon_f, api_key)

                elevation = None
                is_mountainous = False
                if auto_elev:
                    elev = fetch_elevation(lat_f, lon_f)
                    if elev is not None:
                        elevation = elev
                        is_mountainous = elev >= ELEVATION_MOUNTAIN_THRESHOLD
                    else:
                        elevation = None
                        is_mountainous = False

                # override if user forces
                if force_mountain:
                    is_mountainous = True

        # Run analysis
        result = analyze_risk(weather_json, is_mountainous)

        # Display results
        st.header(f"Risk level: {result['level']}")
        st.subheader("Why this assessment?")
        for r in result["reasons"]:
            st.write("- " + r)

        st.subheader("Recommendations")
        for a in result["advice"]:
            st.write("- " + a)

        st.markdown("---")
        st.subheader("Weather snapshot (raw values)")
        raw = result["raw"]
        st.write(f"Temperature: {raw.get('temp_c', 'N/A')} °C")
        st.write(f"Weather: {raw.get('weather_main', '')} — {raw.get('weather_desc','')}")
        st.write(f"Wind speed: {raw.get('wind_speed', 'N/A')} m/s")
        st.write(f"Rain (1h): {raw.get('rain_1h', 0.0)} mm")
        st.write(f"Snow (1h): {raw.get('snow_1h', 0.0)} mm")
        if elevation is not None:
            st.write(f"Elevation (auto-detected): {elevation} m")
            st.write(f"Mountainous (threshold {ELEVATION_MOUNTAIN_THRESHOLD} m): {'Yes' if is_mountainous else 'No'}")
        else:
            st.write("Elevation: N/A (provide lat/lon and enable auto-detect to fetch elevation).")
    except requests.HTTPError as he:
        st.error(f"External API HTTP error: {he}")
    except Exception as e:
        st.error(f"An error occurred: {e}")

st.markdown("---")
st.caption("This app gives a simple, conservative assessment and is for guidance only — always check local authorities and live weather/alerts before travelling.")
