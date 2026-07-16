"""
DLX Multi-Downloader Bot v2
-----------------------------
- Universal link downloader (yt-dlp: YouTube, TikTok, Facebook, Instagram, X, etc.)
- Quality selection (Best / 720p / 480p / Audio-MP3)
- Force-Join after free-download limit
- Real AdsGram ad shown mid-download (https://docs.adsgram.ai)
- Telegram Stars (XTR) support/donation to the bot owner
 
Run: python bot.py
"""
 
import asyncio
import json
import logging
import os
import uuid
 
import httpx
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Update,
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)
from yt_dlp import YoutubeDL
 
# ============================================================
# ================= CONFIGURATION (አርትዕ አድርግ) =================
# ============================================================
 
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
 
MAIN_CHANNEL_USERNAME = "@your_channel"           # Force-join channel
MAIN_CHANNEL_LINK = "https://t.me/your_channel"
 
ADMIN_IDS = [123456789]
 
FREE_DOWNLOADS = 3          # free downloads before force-join kicks in
 
# ---- AdsGram configuration ----
# ከ https://partner.adsgram.ai ትፈጥራለህ (ከታች ባለው ማብራሪያ ላይ ዝርዝር አለ)
ADSGRAM_ENABLED = True
ADSGRAM_BLOCK_ID = "YOUR_BLOCK_ID"          # numeric only, no "bot-" prefix
ADSGRAM_TOKEN = "YOUR_ADSGRAM_TOKEN"        # from your AdsGram profile
ADSGRAM_LANGUAGE = "en"
ADSGRAM_API_URL = "https://api.adsgram.ai/advbot"
AD_DISPLAY_SECONDS = 4
 
# fallback ad (used if AdsGram has no fill / is disabled)
FALLBACK_AD_TEXT = (
    "📢 <b>Sponsored</b>\n\nYour ad slot is empty right now.\n"
    "Contact @your_ad_channel to advertise here."
)
FALLBACK_AD_BUTTON_TEXT = "🔗 Learn more"
FALLBACK_AD_BUTTON_URL = "https://t.me/your_ad_channel"
 
# ---- Telegram Stars (donations to bot owner) ----
STARS_ENABLED = True
STARS_PRESET_AMOUNTS = [15, 50, 100, 250]     # amounts in Stars
 
DOWNLOAD_DIR = "downloads"
USERS_DB_FILE = "users_db.json"
MAX_TELEGRAM_FILE_MB = 50
 
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
            rec = {"downloads": 0, "verified": False, "stars_donated": 0}
            db[str(user_id)] = rec
            _save_db(db)
        return rec
 
 
async def increment_user_downloads(user_id: int) -> int:
    async with _db_lock:
        db = _load_db()
        rec = db.setdefault(str(user_id), {"downloads": 0, "verified": False, "stars_donated": 0})
        rec["downloads"] += 1
        _save_db(db)
        return rec["downloads"]
 
 
async def mark_verified(user_id: int) -> None:
    async with _db_lock:
        db = _load_db()
        rec = db.setdefault(str(user_id), {"downloads": 0, "verified": False, "stars_donated": 0})
        rec["verified"] = True
        _save_db(db)
 
 
async def add_stars_donation(user_id: int, amount: int) -> None:
    async with _db_lock:
        db = _load_db()
        rec = db.setdefault(str(user_id), {"downloads": 0, "verified": False, "stars_donated": 0})
        rec["stars_donated"] = rec.get("stars_donated", 0) + amount
        _save_db(db)
 
 
async def all_users_count() -> int:
    async with _db_lock:
        return len(_load_db())
 
 
async def total_stars_donated() -> int:
    async with _db_lock:
        db = _load_db()
        return sum(rec.get("stars_donated", 0) for rec in db.values())
 
 
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
    user_id = update.effective_user.id
    rec = await get_user_record(user_id)
 
    if rec["downloads"] < FREE_DOWNLOADS or rec.get("verified"):
        return True
 
    if await is_member_of_channel(context, user_id):
        await mark_verified(user_id)
        return True
 
    text = (
        "🚫 <b>ነጻ ማውረጃ አልቋል!</b>\n\n"
        f"ያለክፍያ የሚፈቀደው {FREE_DOWNLOADS} ማውረድ ተጠናቋል።\n"
        "ቦቱን መጠቀም እንድትቀጥል የቻናላችንን አባል ሁን፣ ከዛ <b>✅ I Joined</b> ን ተጫን።"
    )
    await update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=join_required_keyboard()
    )
    return False
 
 
# ============================================================
# ======================= ADSGRAM AD ==========================
# ============================================================
 
async def fetch_adsgram_ad(tgid: int) -> dict | None:
    """Calls the real AdsGram API. Returns None if disabled/no-fill/error."""
    if not ADSGRAM_ENABLED or ADSGRAM_BLOCK_ID == "YOUR_BLOCK_ID":
        return None
 
    params = {
        "tgid": tgid,
        "blockid": ADSGRAM_BLOCK_ID,
        "language": ADSGRAM_LANGUAGE,
        "token": ADSGRAM_TOKEN,
    }
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            resp = await client.get(ADSGRAM_API_URL, params=params)
            if resp.status_code != 200:
                logger.info("AdsGram no-fill or error: %s", resp.status_code)
                return None
            data = resp.json()
            if not data.get("text_html"):
                return None
            return data
    except Exception as e:
        logger.warning("AdsGram request failed: %s", e)
        return None
 
 
async def show_ad(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    """
    Shows a real AdsGram ad if available, otherwise a fallback sponsor slot.
    protect_content=True keeps the ad from being forwarded (AdsGram requirement).
    """
    ad = await fetch_adsgram_ad(user_id)
 
    if ad:
        buttons = [[InlineKeyboardButton(ad["button_name"], url=ad["click_url"])]]
        if ad.get("reward_url") and ad.get("button_reward_name"):
            buttons.append(
                [InlineKeyboardButton(ad["button_reward_name"], url=ad["reward_url"])]
            )
        try:
            if ad.get("image_url"):
                msg = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=ad["image_url"],
                    caption=ad["text_html"],
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(buttons),
                    protect_content=True,
                )
            else:
                msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=ad["text_html"],
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(buttons),
                    protect_content=True,
                )
        except Exception as e:
            logger.warning("Failed sending AdsGram ad, falling back: %s", e)
            msg = await _send_fallback_ad(context, chat_id)
    else:
        msg = await _send_fallback_ad(context, chat_id)
 
    await asyncio.sleep(AD_DISPLAY_SECONDS)
    return msg
 
 
async def _send_fallback_ad(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(FALLBACK_AD_BUTTON_TEXT, url=FALLBACK_AD_BUTTON_URL)]]
    )
    return await context.bot.send_message(
        chat_id=chat_id,
        text=FALLBACK_AD_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        protect_content=True,
    )
 
 
# ============================================================
# ========================= COMMANDS ==========================
# ============================================================
 
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await get_user_record(update.effective_user.id)
    text = (
        "👋 <b>Welcome to DLX Multi-Downloader!</b>\n\n"
        "🎬 ማንኛውንም ቪድዮ ሊንክ ላክልኝ (YouTube, TikTok, Facebook, Instagram, X, ወዘተ) "
        "እኔ ደግሞ በምትፈልገው ጥራት <b>Video</b> ወይም <b>Audio (MP3)</b> አድርጌ አወርድልሃለሁ።\n\n"
        f"ℹ️ ያለ ክፍያ {FREE_DOWNLOADS} ጊዜ ማውረድ ትችላለህ/ሽ። ከዛ ቻናላችንን መቀላቀል ያስፈልጋል።\n\n"
        "⭐ ቦቱን መደገፍ ከፈለክ /donate ብለህ ላክ።"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
 
 
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    users = await all_users_count()
    stars = await total_stars_donated()
    await update.message.reply_text(
        f"👥 Total users: {users}\n⭐ Total Stars donated: {stars}"
    )
 
 
# ---- Telegram Stars donation flow ----
 
async def donate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not STARS_ENABLED:
        await update.message.reply_text("⭐ Donations are currently disabled.")
        return
    buttons = [
        [InlineKeyboardButton(f"⭐ {amt} Stars", callback_data=f"donate:{amt}")]
        for amt in STARS_PRESET_AMOUNTS
    ]
    await update.message.reply_text(
        "⭐ <b>Support DLX Multi-Downloader</b>\n\n"
        "ቦቱ ነጻ ሆኖ እንዲቆይ የፈለከውን መጠን Telegram Stars ልትደግፍ ትችላለህ/ሽ 🙏",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )
 
 
async def donate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, amount_str = query.data.split(":", 1)
    amount = int(amount_str)
 
    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=f"Support DLX Bot - {amount} Stars",
        description="Thank you for supporting the development of this bot! ⭐",
        payload=f"stars_donation_{amount}_{query.from_user.id}",
        provider_token="",          # empty string required for Telegram Stars (XTR)
        currency="XTR",
        prices=[LabeledPrice(label="Donation", amount=amount)],
    )
 
 
async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)
 
 
async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    amount = payment.total_amount  # amount is already in Stars for XTR
    await add_stars_donation(update.effective_user.id, amount)
    await update.message.reply_text(
        f"🎉 አመሰግናለሁ! {amount} ⭐ Stars ተቀብያለሁ። ድጋፍህ በጣም ይረዳል!"
    )
 
 
# ============================================================
# ===================== LINK / DOWNLOAD =======================
# ============================================================
 
QUALITY_OPTIONS = [
    ("🎥 Best Quality", "best"),
    ("📺 720p", "720"),
    ("📱 480p", "480"),
    ("🎵 Audio (MP3)", "audio"),
]
 
 
def _quality_keyboard(token: str) -> InlineKeyboardMarkup:
    rows, row = [], []
    for label, key in QUALITY_OPTIONS:
        row.append(InlineKeyboardButton(label, callback_data=f"dl:{key}:{token}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)
 
 
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await enforce_join_if_needed(update, context):
        return
 
    url = update.message.text.strip()
    if not url.lower().startswith(("http://", "https://")):
        await update.message.reply_text("⚠️ እባክህ/ሽ ትክክለኛ ሊንክ ላክ/ኪ።")
        return
 
    token = uuid.uuid4().hex[:10]
    context.bot_data.setdefault("pending_links", {})[token] = url
 
    await update.message.reply_text(
        "🔎 ሊንኩን አገኘሁት! የምትፈልገውን ጥራት ምረጥ/ጪ፡",
        reply_markup=_quality_keyboard(token),
    )
 
 
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
 
    if data == "check_join":
        await query.answer()
        user_id = query.from_user.id
        if await is_member_of_channel(context, user_id):
            await mark_verified(user_id)
            await query.edit_message_text("✅ አመሰግናለሁ! አሁን ቦቱን መጠቀም ትችላለህ/ሽ። ሊንክ ላክ/ኪ።")
        else:
            await query.answer("❌ ገና አልተቀላቀልክም/ም። እባክህ/ሽ መጀመሪያ ቻናሉን ተቀላቀል/ይ።", show_alert=True)
        return
 
    if data.startswith("donate:"):
        await donate_callback(update, context)
        return
 
    if data.startswith("dl:"):
        await query.answer()
        _, quality, token = data.split(":", 2)
        url = context.bot_data.get("pending_links", {}).get(token)
        if not url:
            await query.edit_message_text("⚠️ ይህ ሊንክ ጊዜው አልፎበታል፣ እባክህ/ሽ እንደገና ላክ/ኪ።")
            return
 
        as_audio = quality == "audio"
        await query.edit_message_text("⏳ በማውረድ ላይ... እባክህ/ሽ ትንሽ ትዕግስት አድርግ/ጊ።")
 
        chat_id = query.message.chat_id
        user_id = query.from_user.id
 
        # --- Show AdsGram (or fallback) ad while the download happens ---
        ad_task = asyncio.create_task(show_ad(context, chat_id, user_id))
        download_task = asyncio.create_task(do_download(url, quality=quality))
        ad_msg, result = await asyncio.gather(ad_task, download_task)
 
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
                with open(filepath, "rb") as f:
                    if as_audio:
                        await context.bot.send_audio(chat_id, audio=f, caption="🎵 DLX Multi-Downloader")
                    else:
                        await context.bot.send_video(
                            chat_id, video=f, caption="🎬 DLX Multi-Downloader", supports_streaming=True
                        )
            except Exception as e:
                await context.bot.send_message(chat_id, f"❌ መላክ አልተቻለም: {e}")
 
        try:
            os.remove(filepath)
        except OSError:
            pass
 
        await increment_user_downloads(user_id)
        context.bot_data.get("pending_links", {}).pop(token, None)
 
 
# ============================================================
# ======================= YT-DLP LOGIC =========================
# ============================================================
 
QUALITY_FORMAT_MAP = {
    "best": "best[filesize<50M]/best",
    "720": "best[height<=720][filesize<50M]/best[height<=720]",
    "480": "best[height<=480][filesize<50M]/best[height<=480]",
}
 
 
async def do_download(url: str, quality: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _blocking_download, url, quality)
 
 
def _blocking_download(url: str, quality: str) -> dict:
    out_template = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex}.%(ext)s")
    as_audio = quality == "audio"
 
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
        ydl_opts["format"] = QUALITY_FORMAT_MAP.get(quality, QUALITY_FORMAT_MAP["best"])
 
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            if as_audio:
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
    app.add_handler(CommandHandler("donate", donate_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
 
    logger.info("DLX Multi-Downloader Bot v2 starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
 
 
if __name__ == "__main__":
    main()
