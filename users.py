"""
upload_users.py — Save users.json to Railway volume by pasting JSON directly.

No file download needed — just paste the JSON text in chat.

HOW TO USE:
  1. Open your users.json file on your computer
  2. Copy ALL the text inside it
  3. Send /uploadusers to the bot
  4. Paste the copied JSON text and send it
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
from telegram.request import HTTPXRequest

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN   = os.environ["BOT_TOKEN"]
ADMIN_ID    = int(os.environ["ADMIN_ID"])
STORAGE_DIR = Path(os.environ.get("STORAGE_PATH", "/data"))
USERS_FILE  = Path(os.environ.get("USERS_FILE", str(STORAGE_DIR / "users.json")))

AWAIT_JSON = 0


# ── Handlers ──────────────────────────────────────────────────────────────────
async def start_upload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admins only.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📋 *Paste your users.json content*\n\n"
        "1. Open users.json on your computer\n"
        "2. Select all text (Ctrl+A / Cmd+A)\n"
        "3. Copy it (Ctrl+C / Cmd+C)\n"
        "4. Paste it here and send\n\n"
        "Use /cancel to abort.",
        parse_mode="Markdown",
    )
    return AWAIT_JSON


async def receive_json(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admins only.")
        return ConversationHandler.END

    text = update.message.text or ""
    if not text.strip():
        await update.message.reply_text("⚠️ Got an empty message. Please paste your JSON text.")
        return AWAIT_JSON

    # Validate JSON
    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError as e:
        await update.message.reply_text(
            f"❌ Invalid JSON: {e}\n\n"
            "Make sure you copied the entire file content."
        )
        return AWAIT_JSON

    # Count users
    if isinstance(data, dict):
        users = data.get("users", data)
    else:
        users = data
    user_count = len(users)

    if user_count == 0:
        await update.message.reply_text(
            "⚠️ No users found in the JSON. Double-check the content."
        )
        return AWAIT_JSON

    # Save atomically to Railway volume
    try:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        tmp = USERS_FILE.with_suffix(".tmp")
        tmp.write_bytes(raw)
        tmp.replace(USERS_FILE)
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to save to disk: {e}")
        return ConversationHandler.END

    logger.info("users.json saved to %s (%d users)", USERS_FILE, user_count)
    await update.message.reply_text(
        f"✅ *Saved successfully!*\n\n"
        f"📍 `{USERS_FILE}`\n"
        f"👥 Users: *{user_count}*\n\n"
        f"Stop this service and restart your main bot.\n"
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
    request = HTTPXRequest(connect_timeout=30, read_timeout=60, write_timeout=60)
    app = Application.builder().token(BOT_TOKEN).request(request).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("uploadusers", start_upload)],
        states={
            AWAIT_JSON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_json)
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
