import streamlit as st
import pandas as pd
import os
import folium
import openrouteservice
from geopy.geocoders import Nominatim
from streamlit_folium import st_folium
from streamlit_option_menu import option_menu

API_KEY = st.secrets["ORS_API_KEY"]
PROFILE_FILE = "profiles.csv"

st.set_page_config(page_title="BreathWise AI", page_icon="🌿", layout="wide")

if "route_result" not in st.session_state:
    st.session_state.route_result = None
if "route_error" not in st.session_state:
    st.session_state.route_error = None

st.markdown("""
<style>
.stApp {background: linear-gradient(135deg,#E8F5E9,#F7FFF7);}
section[data-testid="stSidebar"] {background:#E8F5E9;}
.green-header {
    background: linear-gradient(90deg,#BFE8C5,#E8F5E9);
    padding:28px;border-radius:24px;margin-bottom:25px;
    box-shadow:0 6px 20px rgba(0,0,0,0.08);
}
.title {color:#0B5D1E;font-size:42px;font-weight:900;}
.subtitle {color:#2E7D32;font-size:18px;}
.card {
    background:white;padding:22px;border-radius:20px;
    box-shadow:0 5px 18px rgba(0,0,0,0.08);margin-bottom:18px;
}
.route-safe {
    background:linear-gradient(135deg,#F1F8E9,#FFFFFF);
    border:2px solid #43A047;padding:22px;border-radius:20px;
    box-shadow:0 4px 16px rgba(67,160,71,0.18);
}
.route-risk {
    background:linear-gradient(135deg,#FFF3E0,#FFFFFF);
    border:2px solid #FB8C00;padding:22px;border-radius:20px;
    box-shadow:0 4px 16px rgba(251,140,0,0.16);
}
.badge-green {background:#43A047;color:white;padding:6px 12px;border-radius:12px;font-weight:bold;}
.badge-orange {background:#FB8C00;color:white;padding:6px 12px;border-radius:12px;font-weight:bold;}
.small-muted {color:#607D8B;font-size:14px;}
</style>
""", unsafe_allow_html=True)

# ---------------- DATA ----------------
def load_profiles():
    if os.path.exists(PROFILE_FILE):
        return pd.read_csv(PROFILE_FILE)
    return pd.DataFrame(columns=["Name", "Age", "Gender", "Health", "Mask"])

def save_profile(name, age, gender, health, mask):
    df = load_profiles()
    new_data = pd.DataFrame(
        [[name, age, gender, health, mask]],
        columns=["Name", "Age", "Gender", "Health", "Mask"]
    )
    df = pd.concat([df, new_data], ignore_index=True)
    df.to_csv(PROFILE_FILE, index=False)

# ---------------- RISK ----------------
def get_risk_level(aqi):
    if aqi <= 100:
        return "Low"
    elif aqi <= 200:
        return "Medium"
    return "High"

def get_route_color(risk):
    if risk == "Low":
        return "green"
    elif risk == "Medium":
        return "orange"
    return "red"

def get_personal_risk(aqi, health, age, mask):
    risk_score = aqi

    if health in ["Asthma", "COPD / Lung Disease", "Bronchitis"]:
        risk_score += 80
    elif health in ["Heart Problem", "High Blood Pressure"]:
        risk_score += 60
    elif health in ["Elderly / Weak Immunity"]:
        risk_score += 50
    elif health == "Pregnancy":
        risk_score += 50
    elif health == "Sinus / Allergy":
        risk_score += 30

    if age >= 60:
        risk_score += 40
    elif age <= 12:
        risk_score += 35

    if mask == "Yes":
        risk_score -= 30

    if risk_score <= 150:
        return "Low"
    elif risk_score <= 250:
        return "Medium"
    return "High"

# ---------------- MAP ----------------
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

geolocator = Nominatim(
    user_agent="breathewise_ai_project_2026"
)

geocode = RateLimiter(
    geolocator.geocode,
    min_delay_seconds=1
)

def geocode_place(place, context="India"):
    location = geocode(place)

    if location is None:
        location = geocode(f"{place}, {context}")

    if location is None:
        location = geocode(f"{place}, India")

    return location
import requests

def get_openweather_aqi(lat, lon):

    API_KEY_AQI = st.secrets["OPENWEATHER_API_KEY"]

    url = "https://api.openweathermap.org/data/2.5/air_pollution"

    params = {
        "lat": lat,
        "lon": lon,
        "appid": API_KEY_AQI
    }

    response = requests.get(url, params=params)
    data = response.json()

    try:
        aqi_level = data["list"][0]["main"]["aqi"]

        # Convert AQI scale (1-5 → approx AQI value)
        aqi_map = {
            1: 50,
            2: 100,
            3: 150,
            4: 200,
            5: 300
        }

        return aqi_map.get(aqi_level, 150)

    except:
        return 150

@st.cache_data(show_spinner=False)
def create_route_map(start_place, end_place, context):
    start_location = geocode_place(start_place, context)
    end_location = geocode_place(end_place, context)

    if not start_location or not end_location:
        return None, "Location not found. Try clearer names like 'Anna Nagar Chennai'."

    start = (start_location.longitude, start_location.latitude)
    end = (end_location.longitude, end_location.latitude)

    client = openrouteservice.Client(key=API_KEY)

    routes = client.directions(
        coordinates=[start, end],
        profile="driving-car",
        format="geojson",
        alternative_routes={"target_count": 2, "weight_factor": 1.6}
    )
    route_scores = []

    m = folium.Map(
        location=[start_location.latitude, start_location.longitude],
        zoom_start=11
    )

    for i, route in enumerate(routes["features"]):
        distance = route["properties"]["segments"][0]["distance"]

        duration = route["properties"]["segments"][0]["duration"]

        coords = route["geometry"]["coordinates"]

        points = [(coord[1], coord[0]) for coord in coords]

        mid_index = len(coords) // 2
        mid_point = coords[mid_index]

        mid_lat = mid_point[1]
        mid_lon = mid_point[0]

        # Take multiple AQI samples along route

        sample_points = [
            coords[0],                         # Start
            coords[len(coords)//3],            # 1/3 route
            coords[len(coords)//2],            # Mid
            coords[(2*len(coords))//3],        # 2/3 route
            coords[-1]                         # End
        ]

        aqi_values = []

        for pt in sample_points:
            lat = pt[1]
            lon = pt[0]

            aqi_val = get_openweather_aqi(lat, lon)
            aqi_values.append(aqi_val)

        # Average AQI across route
        aqi = int(sum(aqi_values) / len(aqi_values))


        exposure = aqi * (duration / 60)

        if exposure <= 1500:
            risk = "Low"

        elif exposure <= 3000:
            risk = "Medium"

        else:
            risk = "High"
        color = get_route_color(risk)

        exposure_score = aqi * (duration / 60)
        route_scores.append((i + 1, exposure_score, distance, duration, aqi, risk))

        popup_text = f"""
        <b>Route {i+1}</b><br>
        Distance: {round(distance/1000, 2)} km<br>
        Time: {round(duration/60, 2)} minutes<br>
        AQI: {aqi}<br>
        Risk Level: {risk}
        """

        folium.PolyLine(
            locations=points,
            color=color,
            weight=8,
            popup=folium.Popup(popup_text, max_width=300)
        ).add_to(m)

    folium.Marker(
        [start_location.latitude, start_location.longitude],
        popup="Start Location",
        icon=folium.Icon(color="green")
    ).add_to(m)

    folium.Marker(
        [end_location.latitude, end_location.longitude],
        popup="Destination",
        icon=folium.Icon(color="red")
    ).add_to(m)

    legend_html = """
    <div style="position: fixed; bottom: 50px; left: 50px; width: 170px;
    background-color: white; border:2px solid #C8E6C9; z-index:9999;
    font-size:14px; padding: 12px; border-radius: 12px;">
    <b>Route Safety</b><br>
    🟢 Safe Route<br>
    🟠 Medium Risk<br>
    🔴 High Risk<br>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    best_route = min(route_scores, key=lambda x: x[1])
    return (m, route_scores, best_route), None

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding:20px 5px;">
        <div style="font-size:44px;">🌿</div>
        <h2 style="color:#0B5D1E;margin-bottom:0;">BreathWise AI</h2>
        <p style="color:#2E7D32;font-size:14px;">Breathe Better, Travel Smarter</p>
    </div>
    """, unsafe_allow_html=True)

    page = option_menu(
        menu_title=None,
        options=["Dashboard", "Profiles", "Plan Trip", "Health Tips", "About"],
        icons=["house", "person", "map", "heart-pulse", "info-circle"],
        default_index=0,
        styles={
            "container": {"padding": "5px", "background-color": "#E8F5E9"},
            "icon": {"color": "#1B5E20", "font-size": "20px"},
            "nav-link": {
                "font-size": "16px", "text-align": "left", "margin": "8px 0px",
                "padding": "12px", "border-radius": "12px",
                "color": "#1B5E20", "font-weight": "600"
            },
            "nav-link-selected": {
                "background-color": "#2E7D32", "color": "white", "font-weight": "700"
            },
        }
    )

    st.markdown("""
    <div style="margin-top:220px;background:#DFF3E3;padding:16px;border-radius:18px;
    text-align:center;color:#0B5D1E;box-shadow:0 4px 12px rgba(0,0,0,0.08);">
        <h4>🍃 Breathe Smart</h4>
        <p style="font-size:13px;">Choose safe routes, protect your health.</p>
    </div>
    """, unsafe_allow_html=True)

# ---------------- DASHBOARD ----------------
if page == "Dashboard":
    st.markdown("""
    <div class="green-header">
        <div class="title">🌿 BreathWise AI</div>
        <div class="subtitle">Your health-first navigation assistant</div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("🌫️ AQI", "168", "Moderate")
    c2.metric("🛡️ Safety", "Careful", "Precaution needed")
    c3.metric("⏱️ Safe Exposure", "25 min", "Estimated")

    st.markdown("""
    <div class="card">
        <h3>⚠️ Travel Safety Alert</h3>
        <p>Moderate risk detected. Choose a safer route and wear a mask if needed.</p>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("View Detailed Health Impact"):
        st.write("Sensitive users may face breathing discomfort, throat irritation, or fatigue during long exposure.")

# ---------------- PROFILES ----------------
elif page == "Profiles":
    st.markdown("""
    <div class="green-header">
        <div class="title">👤 Profiles</div>
        <div class="subtitle">Create and save passenger health profiles</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)

    name = st.text_input("Name")
    age = st.number_input("Age", 1, 100)
    gender = st.selectbox("Gender", ["Male", "Female"])
    health = st.selectbox("Health Condition", [
        "Healthy", "Asthma", "COPD / Lung Disease", "Bronchitis",
        "Sinus / Allergy", "Heart Problem", "High Blood Pressure",
        "Diabetes", "Pregnancy", "Elderly / Weak Immunity", "Other"
    ])
    mask = st.selectbox("Mask Usage", ["Yes", "No"])

    if st.button("Save Profile 🌿"):
        if name.strip() == "":
            st.error("Name cannot be empty.")
        else:
            save_profile(name, age, gender, health, mask)
            st.success(f"{name} profile saved successfully.")

    st.markdown('</div>', unsafe_allow_html=True)
    
    st.subheader("Saved Profiles")
    st.dataframe(load_profiles(), use_container_width=True)
    st.subheader("Remove Saved Profile")
    profiles_df = load_profiles()
    if not profiles_df.empty:
        delete_name = st.selectbox(
            "Select profile to remove",
            profiles_df["Name"].tolist()
        )

        if st.button("Delete Profile 🗑️"):
            profiles_df = profiles_df[profiles_df["Name"] != delete_name]
            profiles_df.to_csv(PROFILE_FILE, index=False)
            st.success(f"{delete_name} profile removed successfully.")
            st.rerun()
    else:
        st.info("No saved profiles to remove.")

    

# ---------------- PLAN TRIP ----------------
elif page == "Plan Trip":
    st.markdown("""
    <div class="green-header">
        <div class="title">🛣️ Plan Safe Route</div>
        <div class="subtitle">Find the safest low-pollution route</div>
    </div>
    """, unsafe_allow_html=True)

    profiles = load_profiles()
    profile_names = profiles["Name"].tolist() if not profiles.empty else []

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("👥 Passenger Details")

        passengers = st.number_input("Number of Passengers", 1, 6, 1)

        selected_passengers = []

        for i in range(passengers):
            options = profile_names + ["Create New Profile"]

            selected = st.selectbox(
                f"Passenger {i+1} Profile",
                options,
                key=f"passenger_{i}"
            )

            if selected == "Create New Profile":
                st.info(f"Create profile for Passenger {i+1}")

                new_name = st.text_input(f"Passenger {i+1} Name", key=f"new_name_{i}")
                new_age = st.number_input(f"Passenger {i+1} Age", 1, 100, key=f"new_age_{i}")
                new_gender = st.selectbox(f"Passenger {i+1} Gender", ["Male", "Female"], key=f"new_gender_{i}")
                new_health = st.selectbox(
                    f"Passenger {i+1} Health Condition",
                    [
                        "Healthy", "Asthma", "COPD / Lung Disease", "Bronchitis",
                        "Sinus / Allergy", "Heart Problem", "High Blood Pressure",
                        "Diabetes", "Pregnancy", "Elderly / Weak Immunity", "Other"
                    ],
                    key=f"new_health_{i}"
                )
                new_mask = st.selectbox(f"Passenger {i+1} Mask Usage", ["Yes", "No"], key=f"new_mask_{i}")

                if st.button(f"Save Passenger {i+1} Profile", key=f"save_new_{i}"):
                    if new_name.strip() == "":
                        st.error("Name cannot be empty.")
                    else:
                        save_profile(new_name, new_age, new_gender, new_health, new_mask)
                        st.success(f"{new_name} profile saved. Refresh or reselect profile.")

            selected_passengers.append(selected)

        st.markdown('</div>', unsafe_allow_html=True)
    with col2:
        
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("📍 Travel Details")
    
        state_context = st.text_input(
            "City / State / Country",
            "India",
            help="Example: Tamil Nadu India, Delhi India, Karnataka India"
        )
    
        start_place = st.text_input(
            "Start Location",
            "",
            placeholder="Example: Anna Nagar"
        )
    
        end_place = st.text_input(
            "Destination",
            "",
            placeholder="Example: Avadi"
        )
    
        travel_mode = st.selectbox(
            "Travel Mode",
            ["Car", "Bike", "Walking", "Bus", "Metro"]
        )
    
        st.markdown('</div>', unsafe_allow_html=True)

    if st.button("Find Safest Route 🌿", use_container_width=True):
        with st.spinner("Generating safest route..."):
            result, error = create_route_map(start_place, end_place,stste_context)

        st.session_state.route_result = result
        st.session_state.route_error = error

    if st.session_state.route_error:
        st.error(st.session_state.route_error)

    if st.session_state.route_result:
        route_map, route_scores, best_route = st.session_state.route_result

        st.success(f"✅ Recommended Route: Route {best_route[0]}")

        st.subheader("🗺️ Route Map")
        st_folium(
            route_map,
            width=1100,
            height=550,
            returned_objects=[],
            key="route_map_display"
        )

        st.subheader("🛣️ Route Comparison")
        cols = st.columns(len(route_scores))

        for idx, route in enumerate(route_scores):
            route_no, score, distance, duration, aqi, risk = route
            is_best = route_no == best_route[0]
            card_class = "route-safe" if is_best else "route-risk"
            badge = "<span class='badge-green'>⭐ Recommended</span>" if is_best else "<span class='badge-orange'>Alternative</span>"

            with cols[idx]:
                st.markdown(f"""
                <div class="{card_class}">
                    <h3>Route {route_no}</h3>
                    <p>{badge}</p>
                    <hr>
                    <p><b>Distance:</b> {round(distance/1000, 2)} km</p>
                    <p><b>Time:</b> {round(duration/60, 2)} mins</p>
                    <p><b>AQI:</b> {aqi}</p>
                    <p><b>Risk:</b> {risk}</p>
                    <p class="small-muted">Exposure Score: {round(score, 2)}</p>
                </div>
                """, unsafe_allow_html=True)

        # Passenger-wise risk
        st.subheader("👥 Passenger-wise Risk")

        profiles_df = load_profiles()
        passenger_results = []
        best_aqi = best_route[4]

        for passenger in selected_passengers:
            if passenger in profiles_df["Name"].values:
                row = profiles_df[profiles_df["Name"] == passenger].iloc[0]
                p_name = row["Name"]
                p_age = int(row["Age"])
                p_health = row["Health"]
                p_mask = row["Mask"]

                personal_risk = get_personal_risk(best_aqi, p_health, p_age, p_mask)
                passenger_results.append((p_name, personal_risk, p_health))

        if passenger_results:
            for name, risk, health in passenger_results:
                if risk == "High":
                    st.error(f"{name} ({health}) → High Risk ⚠️")
                elif risk == "Medium":
                    st.warning(f"{name} ({health}) → Medium Risk")
                else:
                    st.success(f"{name} ({health}) → Low Risk")
        else:
            st.info("Select saved profiles to view passenger-wise risk.")

        # Overall risk
        st.subheader("⚠️ Overall Travel Safety")

        risks = [r[1] for r in passenger_results]

        if "High" in risks:
            st.error("Overall Risk: HIGH ⚠️ — Some passengers need extra care.")
        elif "Medium" in risks:
            st.warning("Overall Risk: MEDIUM — Travel with precautions.")
        elif "Low" in risks:
            st.success("Overall Risk: LOW — Safe to travel with normal precautions.")
        else:
            st.info("Overall risk will appear after selecting saved passenger profiles.")

        st.subheader("💡 Safety Recommendations")

        st.markdown("""
        <div class="card">
            <p>✔ Choose the recommended low-exposure route</p>
            <p>✔ Keep windows closed while traveling</p>
            <p>✔ Wear N95 mask if AQI is high</p>
            <p>✔ Avoid peak traffic hours when possible</p>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("View Detailed Health Impact"):
            st.write(
                "For sensitive passengers, long exposure may cause breathing discomfort, "
                "throat irritation, eye irritation, or tiredness."
            )

# ---------------- HEALTH TIPS ----------------
elif page == "Health Tips":
    st.markdown("""
    <div class="green-header">
        <div class="title">💡 Health Tips</div>
        <div class="subtitle">Simple steps to reduce pollution exposure</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="card">
        <p>✔ Wear N95 mask during high AQI hours</p>
        <p>✔ Avoid outdoor exercise when AQI is high</p>
        <p>✔ Keep vehicle windows closed in traffic</p>
        <p>✔ Prefer low-pollution routes</p>
        <p>✔ Stay hydrated during long travel</p>
    </div>
    """, unsafe_allow_html=True)

# ---------------- ABOUT ----------------
elif page == "About":
    st.markdown("""
    <div class="green-header">
        <div class="title">ℹ️ About BreathWise AI</div>
        <div class="subtitle">Personalized safe route and pollution exposure assistant</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="card">
        <p>BreathWise AI predicts personal pollution exposure and suggests safer routes based on route pollution, travel mode, passenger health profiles, and exposure time.</p>
        <p>This project is designed to help commuters make safer travel decisions.</p>
    </div>
    """, unsafe_allow_html=True)
