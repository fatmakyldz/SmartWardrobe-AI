import streamlit as st
import os
from auth.auth_manager import AuthManager
from wardrobe.wardrobe_service import WardrobeService
import requests
from PIL import Image
import tensorflow as tf
import numpy as np
import json
from io import BytesIO
from weather.location_service import (
    load_location_data,
    get_cities,
    get_districts,
    get_neighbourhoods
)
from weather.weather_service import get_weather
from ai_assistant.assistant import get_response
from weather.weather_service import test_weather_api
from ai_assistant.outfit_generator import generate_outfit_ai, load_filtered_wardrobe


os.environ["STREAMLIT_WATCHER_TYPE"] = "none"

st.set_page_config(
    page_title="Smart Wardrobe",
    layout="centered"
)


# Yüklenen görseli kaydetme fonksiyonu
def save_uploaded_image(uploaded_image, save_path="uploaded_images"):
    if not os.path.exists(save_path):
        os.makedirs(save_path)  # Eğer klasör yoksa oluştur

    file_path = os.path.join(save_path, uploaded_image.name)
    
    with open(file_path, "wb") as f:
        f.write(uploaded_image.getbuffer())  # Görseli diske kaydediyoruz
    
    return file_path

# Modeli önceden yükleyelim (sadece 1 kere)
@st.cache_resource
def load_model():
    return tf.keras.models.load_model("deepfashion_model.keras", compile=False)


model = load_model()

def analyze_image(image_input):
    print("📷 image type:", type(image_input))
    try:
        # Eğer kullanıcı URL verdiyse
        if isinstance(image_input, str) and image_input.startswith("http"):
            headers = {
                "User-Agent": "Mozilla/5.0"
            }
            response = requests.get(image_input, headers=headers)
            if response.status_code != 200:
                raise ValueError(f"Failed to fetch image from URL: {response.status_code}")
            img = Image.open(BytesIO(response.content))

        # Eğer dosya yüklendiyse
        elif hasattr(image_input, "read"):
            img = Image.open(image_input)

        else:
            raise ValueError("Unsupported image input")

        if img.mode != "RGB":
            img = img.convert("RGB")

        img = img.resize((224, 224))
        img_array = np.array(img) / 255.0
        img_array = np.expand_dims(img_array, axis=0)

        prediction = model.predict(img_array)[0]
        predicted_class = np.argmax(prediction)

        # Klasör isimleri
        class_names = sorted([
            d for d in os.listdir("dataset_by_category")
            if os.path.isdir(os.path.join("dataset_by_category", d))
        ])

        predicted_category = class_names[predicted_class] if predicted_class < len(class_names) else "Unknown"

        return {
            "category": predicted_category,
            "color": "Not detected",  # Color will be entered manually
        }

    except Exception as e:
        print("❌ analyze_image error:", e)
        return {
            "category": "Unknown",
            "color": "Error",
        }


def display_combination(suggestion):
    st.markdown("### 👗 Suggested Outfit")

    explanation = suggestion.get("explanation", "")
    items = suggestion.get("selected_items", [])

    if explanation:
        st.markdown(f"📝 **Why it works:** {explanation}")

    for item in items:
        with st.container():
            st.image(item.get("image_link", ""), width=200)
            st.caption(f"{item.get('name', '')} - {item.get('type', '')}")


auth = AuthManager()

# --- GÜNCEL TASARIM: PASTEL LİLA & CUSTOM CSS ---
st.markdown("""
    <style>
        body {
            background-color: #ffffff;
        }
        h1 {
            color: #e6ccff;
        }
        .stButton > button {
            background-color: #e6ccff;
            color: black;
            border: none;
            border-radius: 8px;
            padding: 8px 16px;
            font-weight: bold;
        }
        .stButton > button:hover {
            background-color: #c499ff;
            color: white;
        }
    </style>
""", unsafe_allow_html=True)

# --- PAGE CONTROL MEKANİĞİ ---
if "page" not in st.session_state:
    st.session_state["page"] = "login"

# --- LOGOUT BUTONU ---
if st.session_state.get("logged_in"):
    if st.button("🔓 Logout", key="logout_btn"):
        st.session_state["logged_in"] = False
        st.session_state["username"] = None
        st.session_state["page"] = "login"
        st.rerun()

# --- GİRİŞ YAPILMAMIŞSA LOGIN SAYFASI ---
if st.session_state["page"] == "login":
    st.title("👗 Smart Wardrobe")

    st.subheader("Welcome to your AI-powered wardrobe!")
    tabs = st.tabs(["📝 Register", "🔐 Login"])

    with tabs[0]:
        st.header("Create a new account")
        username = st.text_input("Username")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm Password", type="password")

        if st.button("Register"):
            success, message = auth.register_user(username, email, password, confirm)
            if success:
                st.success(message)
            else:
                st.error(message)

    with tabs[1]:
        st.header("Login")
        login_email = st.text_input("Email", key="login_email")
        login_password = st.text_input("Password", type="password", key="login_password")

        if st.button("Login"):
            success, message, username = auth.login_user(login_email, login_password)
            if success:
                st.success(message)
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
                st.session_state["page"] = "dashboard"
                st.rerun()
            else:
                st.error(message)

# --- GİRİŞ YAPILDIYSA DASHBOARD SAYFASI ---
elif st.session_state["page"] == "dashboard":
    username = st.session_state["username"]

    st.title(f"✨ Welcome, {username.capitalize()}!")
    st.markdown("Your smart wardrobe assistant is ready. What would you like to do today?")

    # EĞLENCELİ KARTLI DASHBOARD
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 👚 Manage Wardrobe")
        st.image("data/1.webp", width=200)
        st.markdown("<div style='height: 10px'></div>", unsafe_allow_html=True)  # spacing
        if st.button("Go to Wardrobe"):
            st.session_state["page"] = "wardrobe"
            st.rerun()

    with col2:
        st.markdown("#### 🌦️ Weather Assistant")
        st.image("data/3.jpg", width=200)
        st.markdown("<div style='height: 31px'></div>", unsafe_allow_html=True)  # spacing
        if st.button("Check Weather"):
            st.session_state["page"] = "weather"
            st.rerun()

    st.markdown("---")

    col3, col4 = st.columns(2)

    with col3:
        st.markdown("#### 👗 Outfit Recommendation")
        st.image("data/2.jpg", width=200)
        st.markdown("<div style='height: 35px'></div>", unsafe_allow_html=True)  # spacing
        if st.button("Get Outfit Suggestion"):
            st.session_state["page"] = "recommendation"
            st.rerun()


# --- Gardırop Sayfası ---
if st.session_state["page"] == "wardrobe":
    username = st.session_state["username"]
    wardrobe_service = WardrobeService(username)

    st.title(f"👚 Welcome to Your Wardrobe, {username.capitalize()}")
    st.markdown("Here you can manage your clothes and add new items to your wardrobe.")

    # Geri dönme butonu
    if st.button("🔙 Back to Dashboard"):
        st.session_state["page"] = "dashboard"
        st.rerun()

    uploaded_image = st.file_uploader("Upload Clothing Image", type=["jpg", "png", "jpeg"])
    image_url = st.text_input("Enter image URL (or leave blank if you uploaded a file):")

    # Tahmin edilecek alanlar (önceden boş tanımla!)
    predicted_category = ""

    item_info = None
    image_input = None

    if image_url:
        image_input = image_url
    elif uploaded_image:
        image_input = uploaded_image
    else:
        image_input = None

    item_info = None
    if image_input:
        st.image(image_input, caption="Clothing Image", width=200)
        item_info = analyze_image(image_input)
        st.success(f"Clothing details: {item_info}")

    if item_info:
        predicted_category = item_info["category"]

    # Giriş alanları (AI varsa otomatik dolu gelir)
    name = st.text_input("Clothing Name")
    categories = ["Tops", "Bottoms", "Dresses", "Outerwear", "Shoes", "Accessories"]
    ctype = st.selectbox("Category", categories, index=categories.index(predicted_category) if predicted_category in categories else 0)

    color = st.text_input("Color")  # Kullanıcıdan rengi alıyoruz.

    weather_tags = st.multiselect("Weather Tags", ["Hot", "Cold", "Rainy", "Windy"])
    event_tags = st.multiselect("Event Tags", ["Casual", "Business", "Party", "Sport"])

    if st.button("Add to Wardrobe"):
        if name:
            # 👇 görsel dosyasını kaydet ve path'i al
            image_link = ""
            if uploaded_image:
                image_link = save_uploaded_image(uploaded_image)
            elif image_url:
                image_link = image_url

            item_data = {
                "name": name,
                "type": ctype,
                "color": color,
                "weather_tags": weather_tags,
                "event_tags": event_tags,
                "image_link": image_link
            }
            wardrobe_service.add_item(item_data)
            st.success("✅ Clothing added successfully!")
        else:
            st.error("🚨 Please fill in all required fields.")

    st.subheader("Your Wardrobe")
    wardrobe_data = wardrobe_service.load_wardrobe()
    if wardrobe_data:
        for item in wardrobe_data:
            st.markdown(f"**{item['name']}** - {item['type']}")
            st.image(item['image_link'], width=100)
            st.write(f"Color: {item['color']}")
            st.write(f"Weather: {', '.join(item['weather_tags'])}, Events: {', '.join(item['event_tags'])}")
            st.markdown("---")
    else:
        st.info("Your wardrobe is empty. Add some items!")


elif st.session_state["page"] == "weather":
    from weather.location_service import (
        load_location_data,
        get_cities,
        get_districts,
        get_neighbourhoods
    )
    from weather.weather_service import get_weather
    from ai_assistant.assistant import get_response

    st.markdown("<h2 style='color:#c499ff'>🌤️ Smart Weather Assistant</h2>", unsafe_allow_html=True)
    st.markdown("👗 I'm your AI stylist! Let's get you ready for the day.")

    st.markdown("---")

    # 🔍 Konum seçimi
    location_data = load_location_data()
    col1, col2, col3 = st.columns(3)

    with col1:
        city = st.selectbox("Select City", get_cities(location_data))
    with col2:
        district = st.selectbox("Select District", get_districts(location_data, city))
    with col3:
        neighbourhood = st.selectbox("Select Neighbourhood", get_neighbourhoods(location_data, city, district))

    full_address = f"{neighbourhood}, {district}, {city}, Turkey"
    st.write("📍 Full address:", full_address)

    temperature = get_weather(full_address)
    
    if temperature is not None:
        st.success(f"📍 Weather in {neighbourhood}, {district}: **{temperature}°C**")

        st.markdown("---")
        st.markdown("💬 <b>Tell me what you're planning today:</b>", unsafe_allow_html=True)

        user_input = st.text_area("Type your plan here...", height=100, placeholder="e.g. I'm going for coffee with friends.")

        if st.button("🧠 Ask Assistant"):
            with st.spinner("Thinking..."):
                try:
                    reply = get_response(user_input, temperature)
                    st.markdown(f"🤖 **AI Assistant:** {reply}")
                except Exception as e:
                    st.error(f"❌ Assistant Error: {e}")
    else:
        st.warning("⚠️ Couldn't fetch weather data for the selected location. Please try a nearby district or check your connection.")

elif st.session_state["page"] == "recommendation":
    st.title("👗 Smart Outfit Recommendation")

    location_data = load_location_data()
    col1, col2, col3 = st.columns(3)
    with col1:
        city = st.selectbox("City", get_cities(location_data))
    with col2:
        district = st.selectbox("District", get_districts(location_data, city))
    with col3:
        neighbourhood = st.selectbox("Neighbourhood", get_neighbourhoods(location_data, city, district))

    full_address = f"{neighbourhood}, {district}, {city}, Turkey"
    temperature = get_weather(full_address)

    event_type = st.selectbox("What's the event?", ["Party", "Business", "Casual", "Sport"])

    if st.button("🎯 Generate Outfit"):
        with st.spinner("AI is building your outfit..."):
            username = st.session_state["username"]
            filtered_items = load_filtered_wardrobe(event_type, temperature, username)
            suggestion = generate_outfit_ai(filtered_items, event_type, temperature)
            display_combination(suggestion)  

    if st.button("🔙 Back to Dashboard"):
        st.session_state["page"] = "dashboard"
        st.rerun()

