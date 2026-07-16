 PY
"""
DLX Multi-Downloader Bot
-------------------------
Video/Audio downloader Telegram bot with:
  - Ad message shown mid-download (sponsored message / button)
  - Force-Join system: after a user exceeds a free-download limit,
    they must join the main channel to continue
  - Video -> Audio (MP3) conversion using yt-dlp + ffmpeg
 
Requirements: see requirements.txt
Run: python bot.py
"""
 
import asyncio
import json
import logging
import os
import uuid
 
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from yt_dlp import YoutubeDL
 
# ============================================================
# ================= CONFIGURATION (አርትዕ አድርግ) =================
# ============================================================
 
BOT_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"          # @BotFather ላይ የተቀበልከው ቶክን
 
MAIN_CHANNEL_USERNAME = "@your_channel"        # Force-join የሚሆነው ዋና ቻናል (username)
MAIN_CHANNEL_LINK = "https://t.me/your_channel"  # ተጠቃሚው ላይ የሚታይ ሊንክ
 
ADMIN_IDS = [123456789]                        # የAdmin telegram user id(s)
 
FREE_DOWNLOADS = 3          # ያለ join ስንት ጊዜ ማውረድ ይችላል (ተደጋጋሚ ሲሆን join ይገደዳል)
 
# ---- ማስታወቂያ (Ad) ማስተካከያ ----
AD_TEXT = (
    "📢 *Sponsored*\n\n"
    "Your Ad / Sponsor message here.\n"
    "Contact @your_ad_channel for advertising."
)
AD_BUTTON_TEXT = "🔗 Visit Sponsor"
AD_BUTTON_URL = "https://t.me/your_ad_channel"
AD_DISPLAY_SECONDS = 4          # ማስታወቂያው ስንት ሰከንድ እንደሚታይ
 
DOWNLOAD_DIR = "downloads"
USERS_DB_FILE = "users_db.json"
MAX_TELEGRAM_FILE_MB = 50        # Bot API upload limit (normal bot token)
 
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("dlx-bot")
 
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
 
# ============================================================
# ==================== SIMPLE JSON "DB" =====================
# ============================================================
 
_db_lock = asyncio.Lock()
 
 
def _load_db() -> dict:
    if not os.path.exists(USERS_DB_FILE):
        return {}
    try:
        with open(USERS_DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
 
 
def _save_db(data: dict) -> None:
    with open(USERS_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
 
 
async def get_user_record(user_id: int) -> dict:
    async with _db_lock:
        db = _load_db()
        rec = db.get(str(user_id))
        if rec is None:
            rec = {"downloads": 0, "verified": False}
            db[str(user_id)] = rec
            _save_db(db)
        return rec
 
 
async def increment_user_downloads(user_id: int) -> int:
    async with _db_lock:
        db = _load_db()
        rec = db.setdefault(str(user_id), {"downloads": 0, "verified": False})
        rec["downloads"] += 1
        _save_db(db)
        return rec["downloads"]
 
 
async def mark_verified(user_id: int) -> None:
    async with _db_lock:
        db = _load_db()
        rec = db.setdefault(str(user_id), {"downloads": 0, "verified": False})
        rec["verified"] = True
        _save_db(db)
 
 
async def all_users_count() -> int:
    async with _db_lock:
        return len(_load_db())
 
 
# ============================================================
# =================== FORCE JOIN HELPERS =====================
# ============================================================
 
async def is_member_of_channel(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(MAIN_CHANNEL_USERNAME, user_id)
        return member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except Exception as e:
        logger.warning("Membership check failed for %s: %s", user_id, e)
        return False
 
 
def join_required_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➡️ Join Channel", url=MAIN_CHANNEL_LINK)],
            [InlineKeyboardButton("✅ I Joined - Try Again", callback_data="check_join")],
        ]
    )
 
 
async def enforce_join_if_needed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Returns True if the user is allowed to continue.
    If the free-download limit is passed and the user is not a channel
    member, sends a force-join prompt and returns False.
    """
    user_id = update.effective_user.id
    rec = await get_user_record(user_id)
 
    if rec["downloads"] < FREE_DOWNLOADS or rec.get("verified"):
        return True
 
    if await is_member_of_channel(context, user_id):
        await mark_verified(user_id)
        return True
 
    text = (
        "🚫 *ነጻ ማውረጃ አልቋል!*\n\n"
        f"ያለክፍያ የሚፈቀደው {FREE_DOWNLOADS} ማውረድ ተጠናቋል።\n"
        "ቦቱን መጠቀም እንድትቀጥል እባክህ/ሽ የቻናላችንን አባል ሁን፣ ከዛ *✅ I Joined* ን ተጫን።"
    )
    await update.effective_message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN, reply_markup=join_required_keyboard()
    )
    return False
 
 
# ============================================================
# ======================= AD (SPONSOR) ========================
# ============================================================
 
async def show_ad(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Send a sponsored/ad message and let it stay visible for a bit
    while the download continues in the background."""
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(AD_BUTTON_TEXT, url=AD_BUTTON_URL)]]
    )
    ad_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=AD_TEXT,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )
    await asyncio.sleep(AD_DISPLAY_SECONDS)
    return ad_msg
 
 
# ============================================================
# ========================= COMMANDS ==========================
# ============================================================
 
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await get_user_record(update.effective_user.id)
    text = (
        "👋 *Welcome to DLX Multi-Downloader!*\n\n"
        "🎬 ማንኛውንም ቪድዮ ሊንክ ላክልኝ (YouTube, TikTok, Facebook, Instagram, ወዘተ) "
        "እኔ ደግሞ *Video* ወይም *Audio (MP3)* አድርጌ አወርድልሃለሁ።\n\n"
        f"ℹ️ ያለ ክፍያ {FREE_DOWNLOADS} ጊዜ ማውረድ ትችላለህ/ሽ። ከዛ በኋላ ቻናላችንን መቀላቀል ያስፈልጋል።"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
 
 
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    count = await all_users_count()
    await update.message.reply_text(f"👥 Total users tracked: {count}")
 
 
# ============================================================
# ===================== LINK / DOWNLOAD =======================
# ============================================================
 
def _fmt_choice_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎥 Video", callback_data=f"dl_video:{token}"),
                InlineKeyboardButton("🎵 Audio (MP3)", callback_data=f"dl_audio:{token}"),
            ]
        ]
    )
 
 
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await enforce_join_if_needed(update, context):
        return
 
    url = update.message.text.strip()
    if not url.lower().startswith(("http://", "https://")):
        await update.message.reply_text("⚠️ እባክህ/ሽ ትክክለኛ ሊንክ ላክ/ኪ።")
        return
 
    # store url under a short token to keep callback_data small
    token = uuid.uuid4().hex[:10]
    context.bot_data.setdefault("pending_links", {})[token] = url
 
    await update.message.reply_text(
        "🔎 ሊንኩን አገኘሁት! ምን አይነት ፋይል ትፈልጋለህ/ጊያለሽ?",
        reply_markup=_fmt_choice_keyboard(token),
    )
 
 
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
 
    if data == "check_join":
        user_id = query.from_user.id
        if await is_member_of_channel(context, user_id):
            await mark_verified(user_id)
            await query.edit_message_text("✅ አመሰግናለሁ! አሁን ቦቱን መጠቀም ትችላለህ/ሽ። ሊንክ ላክ/ኪ።")
        else:
            await query.answer("❌ ገና አልተቀላቀልክም/ም። እባክህ/ሽ መጀመሪያ ቻናሉን ተቀላቀል/ይ።", show_alert=True)
        return
 
    if data.startswith("dl_video:") or data.startswith("dl_audio:"):
        mode, token = data.split(":", 1)
        url = context.bot_data.get("pending_links", {}).get(token)
        if not url:
            await query.edit_message_text("⚠️ ይህ ሊንክ ጊዜው አልፎበታል፣ እባክህ/ሽ እንደገና ላክ/ኪ።")
            return
 
        as_audio = mode == "dl_audio"
        await query.edit_message_text("⏳ በማውረድ ላይ... እባክህ/ሽ ትንሽ ትዕግስት አድርግ/ጊ።")
 
        chat_id = query.message.chat_id
 
        # --- Show a sponsored/ad message while the download happens ---
        ad_task = asyncio.create_task(show_ad(context, chat_id))
        download_task = asyncio.create_task(
            do_download(url, as_audio=as_audio)
        )
        ad_msg, result = await asyncio.gather(ad_task, download_task)
 
        # clean up the ad message so the chat doesn't stay cluttered
        try:
            await context.bot.delete_message(chat_id, ad_msg.message_id)
        except Exception:
            pass
 
        if not result["ok"]:
            await context.bot.send_message(chat_id, f"❌ ስህተት ተፈጥሯል: {result['error']}")
            return
 
        filepath = result["filepath"]
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
 
        if size_mb > MAX_TELEGRAM_FILE_MB:
            await context.bot.send_message(
                chat_id,
                f"⚠️ ፋይሉ በጣም ትልቅ ነው ({size_mb:.1f}MB)። "
                f"Telegram bot ከ{MAX_TELEGRAM_FILE_MB}MB በላይ መላክ አይችልም።",
            )
        else:
            try:
                if as_audio:
                    await context.bot.send_audio(
                        chat_id, audio=open(filepath, "rb"), caption="🎵 DLX Multi-Downloader"
                    )
                else:
                    await context.bot.send_video(
                        chat_id, video=open(filepath, "rb"), caption="🎬 DLX Multi-Downloader",
                        supports_streaming=True,
                    )
            except Exception as e:
                await context.bot.send_message(chat_id, f"❌ መላክ አልተቻለም: {e}")
 
        # cleanup
        try:
            os.remove(filepath)
        except OSError:
            pass
 
        await increment_user_downloads(query.from_user.id)
        context.bot_data.get("pending_links", {}).pop(token, None)
 
 
# ============================================================
# ======================= YT-DLP LOGIC =========================
# ============================================================
 
async def do_download(url: str, as_audio: bool) -> dict:
    """Runs yt-dlp in a background thread so we don't block the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _blocking_download, url, as_audio)
 
 
def _blocking_download(url: str, as_audio: bool) -> dict:
    out_template = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex}.%(ext)s")
 
    ydl_opts = {
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
 
    if as_audio:
        ydl_opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }
        )
    else:
        ydl_opts.update(
            {
                # keep file size reasonable for telegram bot upload limits
                "format": "best[filesize<50M]/best",
            }
        )
 
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            if as_audio:
                # postprocessor changes extension to mp3
                base, _ = os.path.splitext(filepath)
                filepath = base + ".mp3"
        return {"ok": True, "filepath": filepath}
    except Exception as e:
        return {"ok": False, "error": str(e)}
 
 
# ============================================================
# ========================== MAIN ============================
# ============================================================
 
def main():
    app = Application.builder().token(BOT_TOKEN).build()
 
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(callback_router))
 
    logger.info("DLX Multi-Downloader Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
 
 
if __name__ == "__main__":
    main()
