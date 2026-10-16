# 👗 SmartWardrobe

AI outfit suggestions from **your own wardrobe**, for today's weather and wherever you're going.

- Snap a photo of a piece of clothing; AI fills in its category, colours, pattern, warmth and seasons.
- Pick an occasion; get 2-3 outfits built only from items you own, with a short reason for each.
- 👍 / 👎 outfits and future suggestions follow your taste.
- English and Turkish. iOS, Android and web from one Expo app.

> v2 is a rewrite of my 2025 graduation project (Streamlit + TensorFlow). The original is on the [`legacy-streamlit`](https://github.com/fatmakyldz/SmartWardrobe-AI/tree/legacy-streamlit) branch. Progress and decisions: [ROADMAP.md](ROADMAP.md).

## Structure

```
backend/   FastAPI · SQLAlchemy · Alembic · Groq (vision + text) · Open-Meteo
app/       Expo (React Native) · Expo Router — iOS, Android, web
```

## Backend quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env      # add GROQ_API_KEY
alembic upgrade head
uvicorn app.main:app --reload    # http://127.0.0.1:8000/docs
pytest
```

API reference and the AI design: [backend/README.md](backend/README.md).

## App quick start

```bash
cd app
npm install
cp .env.example .env.local    # EXPO_PUBLIC_API_URL
npx expo start                # scan the QR code with Expo Go, or press w for web
```

More in [app/README.md](app/README.md).

## Author

**Fatma Akyıldız** · [FOMER](https://fomertech.com)
