# 👗 Smart Wardrobe - AI-Based Outfit Recommender

Smart Wardrobe is an intelligent outfit recommendation system that combines user wardrobe data, weather forecasting, and event-based logic with AI-powered suggestions to provide personalized clothing recommendations.

🎓 Developed as part of **SEN4018 - Data Science & AI Project** at Bahçeşehir University (Spring 2025).

👥 Team Members:
- **Fatma Akyıldız**
- **Rumeysa Bağıran**

---

## 🚀 Features

- 🔐 Secure login/register system (`auth`)
- 🧳 Wardrobe management interface (`wardrobe`)
- 🌤 Weather-based outfit logic (`weather`)
- 🎯 Event-type specific suggestions
- 🧠 AI-based outfit generation with chat (`ai_assistant`)
- 📸 Image-based prediction for outfit category (optional ML model)
- 📍 Turkish location selector (`turkiye.json`)
- 🗃️ DeepFashion dataset + user-uploaded images for training and prediction

---

## 📁 Project Structure

```
📦 SmartWardrobe/
├── app.py
├── .streamlit/
│   └── secrets.toml
├── ai_assistant/
│   ├── assistant.py
│   └── outfit_generator.py
├── auth/
│   └── auth_manager.py
├── wardrobe/
│   └── wardrobe_service.py
├── weather/
│   └── weather_service.py
│   └── location_service.py
├── recommendation/
│   └── recommender.py
├── utils/
│   ├── hasher.py
│   └── validators.py
├── data/
│   ├── turkiye.json
│   ├── users.json
│   ├── wardrobe_fatma.json
│   ├── 1.webp
│   ├── 2.jpg
│   └── 3.jpg
├── dataset/
│   ├── images/
│   │   └── *.jpg
│   ├── dataset_by_category/
│   │   ├── Accessories/
│   │   ├── Bottoms/
│   │   ├── Dresses/
│   │   ├── Outerwear/
│   │   ├── Shoes/
│   │   └── Tops/
│   ├── images.csv
│   └── styles.csv
├── uploaded_images/
│   ├── bileklik.jpg
│   ├── ceket.jpg
│   ├── çanta.jpg
│   ├── dress.jpg
│   ├── esofman.jpg
│   ├── heels.jpg
│   ├── hırka.jpg
│   ├── kazak.jpg
│   ├── kot.jpg
│   ├── kupe.jpg
│   ├── mont.jpg
│   ├── pink.jpg
│   ├── sneakers.jpg
│   └── tişört.jpg
├── classify_images.py
├── train_model.py
├── deepfashion_model.h5
├── debug.py
├── requirements.txt
└── README.md
```

---

## ⚙️ Setup

### 🔧 Installation

```bash
pip install -r requirements.txt
streamlit run app.py
```

> Make sure to set API keys inside `.streamlit/secrets.toml`.

### 🔑 Required Keys (`.streamlit/secrets.toml`)

```toml
openweather_api = "YOUR_API_KEY"
openrouter_api = "YOUR_API_KEY"
```

---

## 🧠 Tech Stack

- Python 3.10+
- Streamlit
- TensorFlow (image classification)
- OpenWeather API
- Mixtral via OpenRouter.ai
- JSON-based storage (no SQL required)

---

## 👤 Authors

- **Fatma Akyıldız** – Bahçeşehir University  
- **Rumeysa Bağıran** – Bahçeşehir University

---

## 📅 Timeline

| Stage           | Deadline       |
|----------------|----------------|
| Proposal       | March 30, 2025 |
| Dataset Report | April 20, 2025 |
| Final Project  | May 15, 2025   |

---

## 🔒 License

This project is for educational use only. Not intended for commercial deployment.
