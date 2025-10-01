import requests
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta

# Page config
st.set_page_config(
    page_title="Asteroid Impact Simulator ☄",
    page_icon="☄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Title
st.title("🌍 Asteroid Impact Simulator")
st.markdown("""
Welcome to the interactive asteroid impact simulator!  

- Choose a date range for near-Earth objects (NEOs) to analyze.
- Adjust risk thresholds to filter hazardous asteroid impacts.
- Explore interactive visualizations, summary statistics, and detailed asteroid data.
- Download the filtered dataset for offline analysis.
""")

# Parameters Section

with st.form("main_controls_form"):
    st.header(" Simulation Parameters")

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", pd.to_datetime("2025-09-01"))
    with col2:
        end_date = st.date_input("End Date", pd.to_datetime("2025-09-07"))

    col3, col4 = st.columns(2)
    with col3:
        risk_threshold = st.slider(
            "Minimum Impact Energy (Terajoules)",
            min_value=0,
            max_value=50000,
            value=10000,
            help="Filter asteroids by predicted impact energy."
        )
    with col4:
        size_threshold = st.slider(
            "Minimum Diameter (meters)",
            min_value=0,
            max_value=1000,
            value=100,
            help="Filter asteroids by maximum estimated diameter."
        )

    only_hazardous = st.checkbox("Show only potentially hazardous asteroids", value=False)

    submit = st.form_submit_button("Run Simulation")

# NASA API Key + URL
API_KEY = "pSvc7sE9YA14sqLUBvWvofjmzx4sUglGRUG2rh67"
BASE_URL = f"https://api.nasa.gov/neo/rest/v1/feed?api_key={API_KEY}"


# Helper Functions

def get_date_chunks(start_date, end_date, chunk_size=7):
    chunks = []
    current_date = start_date
    while current_date <= end_date:
        chunk_end = min(current_date + timedelta(days=chunk_size - 1), end_date)
        chunks.append((current_date, chunk_end))
        current_date = chunk_end + timedelta(days=1)
    return chunks


@st.cache_data(ttl=3600)
def fetch_asteroid_data_chunk(start: str, end: str) -> pd.DataFrame:
    url = f"{BASE_URL}&start_date={start}&end_date={end}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        asteroids = []
        for day in data.get("near_earth_objects", {}):
            for obj in data["near_earth_objects"][day]:
                cad = obj["close_approach_data"][0]
                asteroids.append({
                    "name": obj.get("name", ""),
                    "approach_date": cad.get("close_approach_date", ""),
                    "size_m": obj["estimated_diameter"]["meters"]["estimated_diameter_max"],
                    "velocity_kph": float(cad["relative_velocity"]["kilometers_per_hour"].replace(",", "")),
                    "miss_distance_km": float(cad["miss_distance"]["kilometers"]),
                    "hazardous": obj.get("is_potentially_hazardous_asteroid", False),
                })
        return pd.DataFrame(asteroids)
    except Exception as e:
        st.error(f"Failed to fetch or parse data for {start} to {end}: {e}")
        return pd.DataFrame()


def fetch_asteroid_data(start_date, end_date) -> pd.DataFrame:
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

    date_chunks = get_date_chunks(start_date, end_date)

    all_asteroids = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, (chunk_start, chunk_end) in enumerate(date_chunks):
        status_text.text(f"Fetching data for {chunk_start} to {chunk_end}...")
        progress_bar.progress((i + 1) / len(date_chunks))

        chunk_df = fetch_asteroid_data_chunk(str(chunk_start), str(chunk_end))
        if not chunk_df.empty:
            all_asteroids.append(chunk_df)

    progress_bar.empty()
    status_text.empty()

    if all_asteroids:
        combined_df = pd.concat(all_asteroids, ignore_index=True)
        combined_df = combined_df.drop_duplicates(subset=['name', 'approach_date'])
        return combined_df
    else:
        return pd.DataFrame()


def calculate_impact_energy(size_m: float, velocity_kph: float) -> float:
    try:
        diameter_m = float(size_m)
        velocity_ms = velocity_kph / 3.6
        volume = (3.14159 / 6) * diameter_m ** 3
        density = 3000  # kg/m^3
        mass = volume * density
        ke_joules = 0.5 * mass * velocity_ms ** 2
        return ke_joules / 4.184e12  # Terajoules
    except Exception:
        return 0.0


# Run Simulation

if submit:
    if start_date > end_date:
        st.error("Error: Start date must be before or the same as End date.")
    else:
        total_days = (end_date - start_date).days + 1
        chunks_needed = (total_days + 6) // 7

        if chunks_needed > 1:
            st.info(f"Processing {total_days} days of data across {chunks_needed} API requests. Please wait...")

        with st.spinner("Fetching asteroid data..."):
            df = fetch_asteroid_data(start_date, end_date)

        if df.empty:
            st.warning("No asteroids found in the selected date range.")
        else:
            df["impact_energy_TJ"] = df.apply(
                lambda row: calculate_impact_energy(row["size_m"], row["velocity_kph"]), axis=1
            )

            mask = (
                    (df["impact_energy_TJ"] >= risk_threshold) &
                    (df["size_m"] >= size_threshold)
            )
            if only_hazardous:
                mask &= df["hazardous"]
            at_risk = df[mask].copy()

            st.markdown("## Summary Statistics")
            if len(at_risk) > 0:
                stats = {
                    "Count": len(at_risk),
                    "Mean Energy (TJ)": round(at_risk["impact_energy_TJ"].mean(), 1),
                    "Max Energy (TJ)": round(at_risk["impact_energy_TJ"].max(), 1),
                    "Mean Size (m)": round(at_risk["size_m"].mean(), 1),
                    "Max Size (m)": round(at_risk["size_m"].max(), 1),
                    "Mean Miss Distance (km)": round(at_risk["miss_distance_km"].mean(), 1),
                }
                st.table(pd.DataFrame.from_dict(stats, orient="index", columns=["Value"]))

                st.markdown(f"### {len(at_risk)} Asteroids Match the Criteria")

                col1, col2 = st.columns([3, 2])
                with col1:
                    scatter = px.scatter(
                        at_risk,
                        x="miss_distance_km",
                        y="impact_energy_TJ",
                        color=at_risk["hazardous"].map({True: "Hazardous", False: "Non-Hazardous"}),
                        hover_name="name",
                        labels={"miss_distance_km": "Miss Distance (km)", "impact_energy_TJ": "Impact Energy (TJ)"},
                        title="Impact Energy vs. Miss Distance",
                        color_discrete_map={"Hazardous": "red", "Non-Hazardous": "green"},
                        template="plotly_dark"
                    )
                    scatter.update_traces(marker=dict(size=10, line=dict(width=1, color="DarkSlateGrey")))
                    st.plotly_chart(scatter, use_container_width=True)

                    hist = px.histogram(
                        at_risk,
                        x="impact_energy_TJ",
                        nbins=30,
                        title="Impact Energy Distribution",
                        labels={"impact_energy_TJ": "Impact Energy (TJ)"},
                        template="plotly_dark"
                    )
                    st.plotly_chart(hist, use_container_width=True)

                with col2:
                    st.subheader("Asteroid Details")
                    display_df = at_risk.copy()
                    display_df["Hazard"] = display_df["hazardous"].apply(
                        lambda x: "HAZARDOUS" if x else "NON-HAZARDOUS")
                    cols = ["Hazard", "name", "approach_date", "size_m", "velocity_kph", "miss_distance_km",
                            "impact_energy_TJ"]
                    st.dataframe(display_df[cols].sort_values("impact_energy_TJ", ascending=False), height=500)

                    csv = at_risk.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label=" Download Data as CSV",
                        data=csv,
                        file_name=f"asteroid_impacts_{start_date}_{end_date}.csv",
                        mime="text/csv"
                    )
            else:
                st.warning("No asteroids match the selected criteria. Try adjusting the filters.")

            st.success(f" Fetched {len(df)} asteroids from {start_date} to {end_date}.")

else:
    st.info(" Set parameters and click 'Run Simulation' to begin.")
