FROM python:3.10-slim

WORKDIR /app

# 依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードのコピー
COPY . .

# 親ディレクトリの database.py や config.py を参照するための工夫は 
# docker-compose のマウントで行うため、ここでは最小限に。
CMD ["python", "bot.py"]