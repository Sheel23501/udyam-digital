# Udyam Digital UI (Streamlit). Talks to the API over HTTP (BACKEND_URL). Build context: frontend/
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 API_MODE=http
WORKDIR /app
# requirements-docker.txt is the slim UI-only list; requirements.txt (full) is for Streamlit Cloud's one-process mode
COPY requirements-docker.txt .
RUN pip install -r requirements-docker.txt
COPY . .
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/_stcore/health' % os.getenv('PORT','8501'), timeout=4)"
CMD ["sh", "-c", "streamlit run app.py --server.port ${PORT:-8501} --server.address 0.0.0.0 --server.headless true"]
