FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# ✅ تحديث yt-dlp لآخر إصدار بعد التثبيت
RUN pip install --upgrade yt-dlp

COPY . .

RUN mkdir -p /app/temp_videos

EXPOSE 7860

CMD ["python", "bot.py"]
