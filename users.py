"""
upload_users.py — Upload users.json to the Railway volume via Telegram.

HOW TO USE:
  1. Stop your main bot (or it will steal the messages)
  2. Deploy this as a separate Railway service with the same env vars
  3. Send /uploadusers to your bot and attach users.json
  4. Once done, stop this service and restart your main bot
"""

import os
import json
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN   = os.environ["BOT_TOKEN"]
ADMIN_ID    = int(os.environ["ADMIN_ID"])          # your Telegram user ID (integer)
STORAGE_DIR = Path(os.environ.get("STORAGE_PATH", "/data"))
USERS_FILE  = Path(os.environ.get("USERS_FILE", str(STORAGE_DIR / "users.json")))

AWAIT_FILE = 0


# ── Handlers ──────────────────────────────────────────────────────────────────
async def start_upload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admins only.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📎 Send your *users.json* file now as a document.\n\n"
        "Use /cancel to abort.",
        parse_mode="Markdown",
    )
    return AWAIT_FILE


async def receive_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admins only.")
        return ConversationHandler.END

    doc = update.message.document
    if doc is None:
        await update.message.reply_text("⚠️ Please send the file as a document (not as a photo/media).")
        return AWAIT_FILE

    # Accept any filename as long as the content is valid JSON
    await update.message.reply_text("⏳ Downloading and validating...")

    try:
        tg_file = await ctx.bot.get_file(doc.file_id)
        raw = await tg_file.download_as_bytearray()
    except Exception as e:
        await update.message.reply_text(f"❌ Download failed: {e}")
        return AWAIT_FILE

    # Validate JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        await update.message.reply_text(f"❌ Invalid JSON: {e}")
        return AWAIT_FILE

    # Count users (handles all formats)
    if isinstance(data, dict):
        users = data.get("users", data)
    else:
        users = data
    user_count = len(users)

    if user_count == 0:
        await update.message.reply_text("⚠️ No users found in the file. Double-check the format.")
        return AWAIT_FILE

    # Save atomically to the Railway volume
    try:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = USERS_FILE.with_suffix(".tmp")
        tmp.write_bytes(raw)
        tmp.replace(USERS_FILE)
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to save file: {e}")
        return AWAIT_FILE

    logger.info("users.json saved to %s (%d users)", USERS_FILE, user_count)
    await update.message.reply_text(
        f"✅ *Saved successfully!*\n\n"
        f"📍 `{USERS_FILE}`\n"
        f"👥 Users: *{user_count}*\n\n"
        f"You can now stop this service and restart your main bot.\n"
        f"Use 📣 Broadcast from the admin menu.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


async def fallback_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send /uploadusers to begin.")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("uploadusers", start_upload)],
        states={
            AWAIT_FILE: [
                MessageHandler(filters.ALL & ~filters.COMMAND, receive_file)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("start", fallback_msg))
    app.add_handler(MessageHandler(filters.ALL, fallback_msg))

    logger.info("Upload bot polling — send /uploadusers in Telegram")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
