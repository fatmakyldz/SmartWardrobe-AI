import json
import openai
import streamlit as st
import os

# ✅ AI üzerinden kombin önerisi yapar
def generate_outfit_ai(wardrobe, event, temperature):
    prompt = (
        f"You are a fashion stylist assistant. The temperature is {temperature}°C "
        f"and the event is '{event}'. Based on the user's wardrobe items below, "
        f"suggest a full outfit (multiple items) that matches both the weather and the event.\n\n"
        f"User's wardrobe:\n{json.dumps(wardrobe, indent=2)}\n\n"
        f"Return a JSON with two keys:\n"
        f"1. selected_items: a list of recommended items (name, type, image_link)\n"
        f"2. explanation: a short description of why this combination works."
    )

    response = get_response_from_openrouter(prompt)
    try:
        suggestion = json.loads(response)
        return suggestion
    except Exception as e:
        print("❌ JSON parsing error:", e)
        return {
            "selected_items": [],
            "explanation": "Failed to parse AI response."
        }

# ✅ OpenRouter üzerinden AI çağrısı yapar
def get_response_from_openrouter(prompt):
    import requests

    api_key = st.secrets["OPENROUTER_API_KEY"]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
    "model": "mistralai/mixtral-8x7b-instruct",
    "messages": [
        {
            "role": "system",
            "content": (
                "You are a fashion AI assistant that suggests outfit combinations "
                "based on weather and event type. You respond only with JSON format "
                "including selected_items and explanation. Do NOT talk like a chatbot."
            )
        },
        {
            "role": "user",
            "content": prompt
        }
    ],
    "temperature": 0.7,
    "max_tokens": 500
    }


    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data
        )

        if response.status_code == 200:
            raw = response.json()
            message = raw["choices"][0]["message"]["content"]
            return message
        else:
            print("❌ OpenRouter API error:", response.status_code, response.text)
            return json.dumps({
                "selected_items": [],
                "explanation": "OpenRouter API failed."
            })

    except Exception as e:
        print("❌ Request error:", e)
        return json.dumps({
            "selected_items": [],
            "explanation": "Exception occurred while contacting OpenRouter API."
        })
def load_filtered_wardrobe(event, temperature, username):
    import json

    wardrobe_path = f"data/wardrobe_{username}.json"
    if not os.path.exists(wardrobe_path):
        return []

    with open(wardrobe_path, "r") as f:
        wardrobe = json.load(f)

    # Hava durumuna göre etiket eşleştirmesi
    weather_tag = ""
    if temperature < 10:
        weather_tag = "Cold"
    elif temperature < 18:
        weather_tag = "Windy"
    elif temperature < 25:
        weather_tag = "Hot"
    else:
        weather_tag = "Hot"

    # Filtreleme
    filtered = [
        item for item in wardrobe
        if weather_tag in item.get("weather_tags", []) and event in item.get("event_tags", [])
    ]
    return filtered