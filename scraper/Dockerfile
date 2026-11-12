FROM python:3.10-slim

WORKDIR /app

# システム依存関係のインストール
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .

# REST API (FastAPI) の起動。UIは frontend コンテナ(Streamlit)が担当
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]