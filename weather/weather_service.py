import requests
from geopy.geocoders import Nominatim
import streamlit as st

def get_weather(location):
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        url = f"http://api.weatherapi.com/v1/current.json?key={api_key}&q={location}&aqi=no"
        
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            st.warning("⚠️ Weather API returned an error.")
            return None

        data = response.json()
        return data["current"]["temp_c"]
        
    except Exception as e:
        st.error(f"❌ Weather fetch failed: {e}")
        return None

def suggest_outfit(temperature):
    if temperature < 10:
        return "🧥 Thick coat, sweater, boots"
    elif temperature < 18:
        return "🧣 Jacket, long-sleeve top, jeans"
    elif temperature < 25:
        return "👕 T-shirt, pants or skirt, sneakers"
    else:
        return "👗 Sleeveless top, shorts, sandals"
def test_weather_api():
    import requests
    api_key = st.secrets["WEATHER_API_KEY"]
    url = f"http://api.weatherapi.com/v1/current.json?key={api_key}&q=Istanbul&aqi=no"

    response = requests.get(url)
    print("Status Code:", response.status_code)
    print("JSON Response:", response.json())
