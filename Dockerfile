FROM python:3.11-slim

WORKDIR /app

# 依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードのコピー
COPY . .

# ポート8000を公開
EXPOSE 8000

# アプリケーションの起動
CMD ["python", "main.py"] 