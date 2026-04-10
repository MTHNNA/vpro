"""handlers.py — Main bot handlers with Arabic UI + audio extraction"""

from aiogram import Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from config import PLATFORM_IDENTIFIERS, extract_url, get_platform_emoji
from handlers.social_media.video_processor import detect_platform_and_process
from utils.user_management import check_channel_subscription, increment_download_count
from utils.common_utils import ensure_user_exists, handle_errors
from utils.rate_limiter import rate_limiter

# Store last URL per user for audio extraction callback
_last_url: dict = {}


class DownloadVideo(StatesGroup):
    waiting_for_link = State()


# ─── /start ───────────────────────────────────────────────────────────────────
async def send_welcome(message: Message, state: FSMContext = None):
    ensure_user_exists(message)
    platforms = sorted(set(PLATFORM_IDENTIFIERS.values()))
    platform_list = "\n".join(
        f"  {get_platform_emoji(p)} {p}" for p in platforms
    )
    text = (
        "👋 *أهلاً بك!*\n\n"
        "⚡ بوت تحميل الفيديوهات والصور والصوت\n\n"
        f"📲 *المنصات المدعومة ({len(platforms)}):*\n"
        f"{platform_list}\n\n"
        "📎 *أرسل الرابط مباشرة!*\n"
        "🎵 *لاستخراج الصوت MP3:* أرسل `/audio` ثم الرابط"
    )
    await message.answer(text, parse_mode="Markdown")


# ─── /help ────────────────────────────────────────────────────────────────────
async def send_help(message: Message):
    text = (
        "❓ *كيفية الاستخدام:*\n\n"
        "▶️ *تحميل فيديو/صور:*\n"
        "  فقط أرسل الرابط مباشرة\n\n"
        "🖼️ *تحميل سلايد شو/كاروسيل:*\n"
        "  أرسل رابط المنشور — يُرسل كل الصور/فيديوهات تلقائياً\n\n"
        "🎵 *استخراج صوت MP3:*\n"
        "  `/audio https://رابط-الفيديو`\n"
        "  أو أرسل الرابط العادي وانقر زر الصوت\n\n"
        "⚙️ *قيود:*\n"
        "• الحد الأقصى للملف: ٥٠ MB\n"
        "• الحسابات الخاصة لا يمكن تحميلها 🔒\n"
        "• ٥ طلبات في الدقيقة لكل مستخدم"
    )
    await message.answer(text, parse_mode="Markdown")


# ─── /audio command ───────────────────────────────────────────────────────────
@handle_errors("⚠️ حدث خطأ، حاول مجدداً")
async def handle_audio_command(message: Message, state: FSMContext):
    user  = ensure_user_exists(message)
    parts = message.text.split(maxsplit=1)

    # /audio with no URL — use last URL
    if len(parts) < 2:
        url = _last_url.get(user["user_id"])
        if not url:
            await message.answer("📎 أرسل: `/audio رابط-الفيديو`", parse_mode="Markdown")
            return
    else:
        url = extract_url(parts[1])

    if not url:
        await message.answer("🔗 أرسل رابطاً صحيحاً بعد `/audio`", parse_mode="Markdown")
        return

    if not rate_limiter.is_allowed(user["user_id"]):
        wait = rate_limiter.seconds_until_allowed(user["user_id"])
        await message.answer(f"⏳ انتظر {wait} ثانية")
        return

    progress_msg = await message.answer("🎵 جاري استخراج الصوت...")
    await detect_platform_and_process(
        message, message.bot, url, progress_msg, audio_only=True
    )
    increment_download_count(user["user_id"])


# ─── Callback: audio extraction button ───────────────────────────────────────
async def handle_audio_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    url = _last_url.get(user_id)
    if not url:
        await callback.answer("❌ لم يتم العثور على الرابط، أرسله مجدداً", show_alert=True)
        return

    await callback.answer("🎵 جاري استخراج الصوت...")
    progress_msg = await callback.message.answer("🎵 جاري استخراج الصوت...")
    await detect_platform_and_process(
        callback.message, callback.bot, url, progress_msg, audio_only=True
    )


# ─── Main URL handler ─────────────────────────────────────────────────────────
@handle_errors("⚠️ حدث خطأ غير متوقع، حاول مجدداً")
async def process_video_link(message: Message, state: FSMContext):
    user    = ensure_user_exists(message)
    user_id = user["user_id"]

    url = extract_url(message.text)
    if not url:
        await message.answer("🔗 أرسل رابطاً صحيحاً يبدأ بـ https://")
        return

    if not rate_limiter.is_allowed(user_id):
        wait = rate_limiter.seconds_until_allowed(user_id)
        await message.answer(f"⏳ انتظر {wait} ثانية قبل الطلب التالي")
        return

    if not await check_channel_subscription(user_id, message.bot):
        return

    # Save URL for audio extraction callback
    _last_url[user_id] = url

    # Detect platform emoji for progress message
    emoji = "🔍"
    for domain, platform in PLATFORM_IDENTIFIERS.items():
        if domain in url:
            emoji = get_platform_emoji(platform)
            break

    progress_msg = await message.answer(f"{emoji} جاري التحليل...")

    detected = await detect_platform_and_process(
        message, message.bot, url, progress_msg, audio_only=False
    )

    if not detected:
        platforms = sorted(set(PLATFORM_IDENTIFIERS.values()))
        await progress_msg.edit_text(
            f"🚫 *المنصة غير مدعومة*\n\nالمنصات: {', '.join(platforms)}",
            parse_mode="Markdown",
        )
        return

    increment_download_count(user_id)

    # Show audio extraction button after successful download
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎵 استخراج الصوت MP3", callback_data="extract_audio"),
        ]])
        await message.answer("⬇️ خيارات إضافية:", reply_markup=keyboard)
    except Exception:
        pass


# ─── Registration ──────────────────────────────────────────────────────────────
def register_handlers(dp):
    dp.message.register(send_welcome,        Command("start"))
    dp.message.register(send_help,           Command("help"))
    dp.message.register(handle_audio_command, Command("audio"))
    dp.message.register(process_video_link,  F.text.regexp(r"https?://"))
    dp.message.register(send_welcome)
    dp.callback_query.register(handle_audio_callback, F.data == "extract_audio")
    print("Main handlers registered")
