# Udyam Digital API. Build context: backend/   (docker compose at the repo root builds it)
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# opencv-python-headless needs libglib at runtime
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY data ./data
COPY scripts ./scripts
COPY tests ./tests
EXPOSE 8000
# Render and most PaaS set $PORT; default 8000 locally. The SQLite file is rebuilt from the CSVs on first start.
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=5 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT','8000'), timeout=4)"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
