import requests
import streamlit as st


def get_response(plan, temperature):
    prompt = f"""
You are a fashion assistant AI. The current temperature is {temperature}°C.
The user provided the following plan: "{plan}"

Based on this, infer the occasion and suggest an outfit using clothing types such as:
- Tops, Dresses, Outerwear, Shoes, Accessories

Suggest a complete and visually pleasing outfit. Avoid suggesting locations or activities.

Respond in this format:
- Suggested Outfit: ...
- Why it works: ...
"""

    headers = {
        "Authorization": f"Bearer {st.secrets['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "mistralai/mixtral-8x7b-instruct",
        "messages": [
            {"role": "system", "content": "You are a helpful fashion AI assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=data
    )

    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        raise Exception(f"API error: {response.status_code}, {response.text}")
