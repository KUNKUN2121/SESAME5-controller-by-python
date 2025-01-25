# Dockerfile

# ベースイメージとしてPython 3.11のスリム版を使用
FROM python:3.11-slim

# 必要なシステムパッケージをインストール
RUN apt-get update && apt-get install -y \
    build-essential \
    libglib2.0-dev \
    bluez \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリを設定
WORKDIR /app

# 依存関係のコピーとインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# ポート5000を公開
EXPOSE 5000

# Flaskアプリケーションを実行
CMD ["python", "app.py"]
