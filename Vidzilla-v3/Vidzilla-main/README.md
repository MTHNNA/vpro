---
title: MU DAV Bot
emoji: 🎬
colorFrom: purple
colorTo: blue
sdk: docker
app_file: bot.py
pinned: false
---

# 🎬 Vidzilla — Video Downloader Telegram Bot

Downloads videos from Instagram, YouTube, TikTok, Facebook, Twitter/X, Pinterest, Reddit, and Vimeo.

## ⚙️ Environment Variables (Secrets)

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | Telegram Bot Token from @BotFather |
| `BOT_MODE` | ✅ | `polling` (recommended) |
| `ADMIN_IDS` | ✅ | Comma-separated Telegram user IDs |
| `MONGODB_URI` | ✅ | MongoDB connection string |
| `MONGODB_DB_NAME` | ✅ | MongoDB database name |
| `MONGODB_USERS_COLLECTION` | ✅ | MongoDB collection name |

> ⚠️ **Important**: HuggingFace Spaces blocks outgoing connections to `api.telegram.org`.
> Deploy on **Koyeb**, **Railway**, or **Render** instead.

## 🚀 Supported Platforms

- YouTube & Shorts
- Instagram Reels & Posts
- TikTok
- Facebook Videos & Reels
- Twitter / X
- Pinterest
- Reddit
- Vimeo
