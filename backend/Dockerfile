FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Hugging Face Spaces runs containers as uid 1000.
RUN useradd -m -u 1000 app && chown -R app:app /app
USER app

ENV PORT=7860
EXPOSE 7860

# Apply database migrations, then serve. Proxy headers are handled inside the app
# (TRUSTED_PROXY_HOSTS), so uvicorn's own handling is off.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-proxy-headers"]
