# 👗 SmartWardrobe – AI-Based Outfit Recommender

SmartWardrobe is an intelligent outfit recommendation system that combines user wardrobe data, real-time weather forecasts, and event-specific logic with AI-powered suggestions.  
The application allows users to securely log in, manage their wardrobe, and receive dynamic outfit recommendations powered by APIs and AI models.

🎓 Developed as an individual graduation project for **SEN4018 - Data Science & AI Project** at Bahçeşehir University (Spring 2025)

👩‍💻 Project Author:  
**Fatma Akyıldız**

---

## 🔴 Live Demo

> 💻 Try it online: [SmartWardrobe Streamlit App](https://smart-wardrobe-57rqfwqnnedmz5nhlonkz4.streamlit.app/)

---

## 🚀 Features

- 🔐 Secure login/register system  
- 🧳 Wardrobe management module  
- 🌦 Weather-based outfit generation (OpenWeatherMap API)  
- 🎯 Event-type specific suggestion logic  
- 🧠 AI-powered assistant using ChatGPT (OpenRouter API)  
- 🧵 Outfit rating with like/dislike feedback  
- 🧠 Optional image-based outfit category prediction (TensorFlow + MobileNetV2)  
- 🌍 Turkish city/region selection using `turkiye.json`  
- 🗃️ DeepFashion dataset support + user-uploaded image handling  

---

## 📁 Project Structure

```
📦 SmartWardrobe/
├── app.py                        # Main app entry point
├── .streamlit/secrets.toml      # API keys for ChatGPT + weather
├── ai_assistant/
│   ├── assistant.py
│   └── outfit_generator.py
├── auth/
│   └── auth_manager.py
├── wardrobe/
│   └── wardrobe_service.py
├── weather/
│   ├── weather_service.py
│   └── location_service.py
├── recommendation/
│   └── recommender.py
├── utils/
│   ├── hasher.py
│   └── validators.py
├── data/
│   ├── turkiye.json
│   ├── users.json
│   └── wardrobe_fatma.json
├── dataset/
│   ├── images/
│   ├── dataset_by_category/
│   ├── images.csv
│   └── styles.csv
├── uploaded_images/
├── classify_images.py
├── train_model.py
├── deepfashion_model.h5
├── requirements.txt
└── README.md
```

---

## ⚙️ Setup & Run (Locally)

```bash
pip install -r requirements.txt
streamlit run app.py
```

### 🔑 Required API Keys (`.streamlit/secrets.toml`)

```toml
openweather_api = "YOUR_OPENWEATHERMAP_KEY"
openrouter_api = "YOUR_OPENROUTER_API_KEY"
```

---

## 🧠 Tech Stack

- Python 3.10+  
- Streamlit (Web UI)  
- OpenWeatherMap API  
- OpenRouter API (ChatGPT / Mixtral)  
- TensorFlow + MobileNetV2  
- JSON-based data storage  

---

## 👩‍💻 Author

**Fatma Akyıldız**  
Final-year Software Engineering student | Specializing in AI-integrated applications  
[GitHub](https://github.com/fatmakyldz) • [LinkedIn](https://www.linkedin.com/in/fatma-akyıldız)

---

## 📜 License

Open-source for academic and personal use.  
Commercial use or redistribution requires written permission.
