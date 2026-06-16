"""
upload_users.py — Standalone bot for uploading users.json to the Railway volume.

Run this SEPARATELY from your main bot (just temporarily).
Send /uploadusers in Telegram, then attach your users.json file.
The bot saves it to /data/users.json on the Railway volume.

Uses the same env vars as your main bot.
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
from telegram.error import TelegramError

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.environ["BOT_TOKEN"]
CHANNEL_ID   = os.environ["CHANNEL_ID"]
GROUP_ID     = os.environ["GROUP_ID"]
STORAGE_DIR  = Path(os.environ.get("STORAGE_PATH", "/data"))
USERS_FILE   = Path(os.environ.get("USERS_FILE", str(STORAGE_DIR / "users.json")))

# ── Conversation state ────────────────────────────────────────────────────────
AWAIT_FILE = 0


# ── Admin check (same logic as main bot) ─────────────────────────────────────
async def is_admin(bot, user_id: int) -> bool:
    for chat_id in [CHANNEL_ID, GROUP_ID]:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            if member.status in ("administrator", "creator"):
                return True
        except TelegramError:
            pass
    return False


# ── Handlers ──────────────────────────────────────────────────────────────────
async def start_upload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(ctx.bot, update.effective_user.id):
        await update.message.reply_text("⛔ Admins only.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📎 Send your *users.json* file now as a document attachment.\n\n"
        "Use /cancel to abort.",
        parse_mode="Markdown",
    )
    return AWAIT_FILE


async def receive_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(ctx.bot, update.effective_user.id):
        await update.message.reply_text("⛔ Admins only.")
        return ConversationHandler.END

    doc = update.message.document
    if not doc.file_name.endswith(".json"):
        await update.message.reply_text(
            "⚠️ That doesn't look like a .json file. Please send your users.json."
        )
        return AWAIT_FILE

    # Download the file
    tg_file = await ctx.bot.get_file(doc.file_id)
    raw = await tg_file.download_as_bytearray()

    # Validate it's proper JSON with a users key
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            users = data.get("users", {})
        elif isinstance(data, list):
            users = data
        else:
            raise ValueError("Unexpected JSON structure")
        user_count = len(users)
    except (json.JSONDecodeError, ValueError) as e:
        await update.message.reply_text(
            f"❌ Invalid JSON file: {e}\n\nPlease check your file and try again."
        )
        return AWAIT_FILE

    # Save to the Railway volume
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = USERS_FILE.with_suffix(".tmp")
    tmp.write_bytes(raw)
    tmp.replace(USERS_FILE)  # atomic rename, same as storage.py

    logger.info("users.json saved to %s (%d users)", USERS_FILE, user_count)
    await update.message.reply_text(
        f"✅ *users.json saved successfully!*\n\n"
        f"📍 Path: `{USERS_FILE}`\n"
        f"👥 Users found: *{user_count}*\n\n"
        f"You can now restart your main bot and use 📣 Broadcast.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


async def unknown(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Use /uploadusers to upload your users.json file."
    )


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    upload_conv = ConversationHandler(
        entry_points=[CommandHandler("uploadusers", start_upload)],
        states={
            AWAIT_FILE: [
                MessageHandler(filters.Document.ALL, receive_file)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(upload_conv)
    app.add_handler(MessageHandler(filters.ALL, unknown))

    logger.info("Upload bot running — send /uploadusers in Telegram")
    app.run_polling()


if __name__ == "__main__":
    main()
