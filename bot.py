import os
import json
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from telegram.error import TelegramError, Forbidden, BadRequest
import storage

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Conversation states ──────────────────────────────────────────────────────
AWAIT_FOLDER_NAME, AWAIT_LOG_CONTENT, AWAIT_LOG_FOLDER, AWAIT_BROADCAST_MSG = range(4)

# ── Users file path (Railway Volume is mounted at /data, same as storage) ────
_STORAGE_DIR = os.environ.get("STORAGE_PATH", "/data")
USERS_FILE   = os.environ.get("USERS_FILE", os.path.join(_STORAGE_DIR, "users.json"))

# ── Config from env ──────────────────────────────────────────────────────────
BOT_TOKEN      = os.environ["BOT_TOKEN"]
CHANNEL_ID     = os.environ["CHANNEL_ID"]
GROUP_ID       = os.environ["GROUP_ID"]
CHANNEL_INVITE = os.environ["CHANNEL_INVITE"]
GROUP_INVITE   = os.environ["GROUP_INVITE"]


# ════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════════════

async def is_admin(bot, user_id: int) -> bool:
    for chat_id in [CHANNEL_ID, GROUP_ID]:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            if member.status in ("administrator", "creator"):
                return True
        except TelegramError:
            pass
    return False


async def is_member(bot, user_id: int) -> bool:
    for chat_id in [CHANNEL_ID, GROUP_ID]:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            if member.status in ("left", "kicked", "banned"):
                return False
        except TelegramError:
            return False
    return True


def membership_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=CHANNEL_INVITE)],
        [InlineKeyboardButton("💬 Join Group",   url=GROUP_INVITE)],
        [InlineKeyboardButton("✅ I've Joined – Check Again", callback_data="check_membership")],
    ])


def main_menu_keyboard(is_adm: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("📂 Browse Logs", callback_data="browse")]]
    if is_adm:
        rows += [
            [InlineKeyboardButton("➕ Add Log",      callback_data="add_log"),
             InlineKeyboardButton("📁 New Folder",   callback_data="add_folder")],
            [InlineKeyboardButton("🗑 Delete Log",   callback_data="delete_log"),
             InlineKeyboardButton("🗂 Delete Folder", callback_data="delete_folder")],
            [InlineKeyboardButton("📣 Broadcast",    callback_data="broadcast")],
        ]
    return InlineKeyboardMarkup(rows)


# ════════════════════════════════════════════════════════════════════════════
#  /start
# ════════════════════════════════════════════════════════════════════════════

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    adm  = await is_admin(ctx.bot, user.id)
    mem  = adm or await is_member(ctx.bot, user.id)

    if not mem:
        await update.message.reply_text(
            "You must join the channel and group to get access.",
            reply_markup=membership_keyboard(),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Select an option:",
        reply_markup=main_menu_keyboard(adm),
    )
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
#  MEMBERSHIP CHECK
# ════════════════════════════════════════════════════════════════════════════

async def check_membership_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    adm  = await is_admin(ctx.bot, user.id)
    mem  = adm or await is_member(ctx.bot, user.id)

    if not mem:
        await query.edit_message_text(
            "You haven't joined both yet. Please join and try again.",
            reply_markup=membership_keyboard(),
        )
        return

    await query.edit_message_text(
        "Select an option:",
        reply_markup=main_menu_keyboard(adm),
    )


# ════════════════════════════════════════════════════════════════════════════
#  MAIN MENU (back button)
# ════════════════════════════════════════════════════════════════════════════

async def main_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    adm = await is_admin(ctx.bot, query.from_user.id)
    await query.edit_message_text(
        "Select an option:",
        reply_markup=main_menu_keyboard(adm),
    )
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
#  BROWSE — folder list → logs in folder
# ════════════════════════════════════════════════════════════════════════════

async def browse_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    adm  = await is_admin(ctx.bot, query.from_user.id)
    mem  = adm or await is_member(ctx.bot, query.from_user.id)

    if not mem:
        await query.edit_message_text(
            "You must join first.",
            reply_markup=membership_keyboard(),
        )
        return

    folders = storage.get_folders()
    if not folders:
        await query.edit_message_text(
            "No folders yet.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]]
            ),
        )
        return

    buttons = [
        [InlineKeyboardButton(
            f"📁 {f['name']}  ({f['coupon_count']} logs)  •  {f['created_at'][:10]}",
            callback_data=f"folder_{f['id']}"
        )]
        for f in folders
    ]
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="main_menu")])
    await query.edit_message_text(
        "Choose a folder:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def folder_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query     = update.callback_query
    await query.answer()
    folder_id = query.data.split("_", 1)[1]
    folder    = storage.get_folder(folder_id)
    logs      = storage.get_coupons(folder_id)

    if not folder:
        await query.edit_message_text("Folder not found.")
        return

    if not logs:
        await query.edit_message_text(
            f"No logs in {folder['name']}.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back", callback_data="browse")]]
            ),
        )
        return

    await query.edit_message_text(
        f"📁 {folder['name']}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back", callback_data="browse")]]
        ),
    )
    for log in logs:
        text = log["code"]
        if log.get("description"):
            text += f"\n{log['description']}"
        await ctx.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
        )


# ════════════════════════════════════════════════════════════════════════════
#  ADMIN — ADD FOLDER
# ════════════════════════════════════════════════════════════════════════════

async def add_folder_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await is_admin(ctx.bot, query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    await query.edit_message_text("Enter folder name:")
    return AWAIT_FOLDER_NAME


async def recv_folder_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Name can't be empty. Try again:")
        return AWAIT_FOLDER_NAME

    storage.create_folder(name)
    adm = await is_admin(ctx.bot, update.effective_user.id)
    await update.message.reply_text(
        f"✅ Folder \"{name}\" created.",
        reply_markup=main_menu_keyboard(adm),
    )
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
#  ADMIN — ADD LOG
# ════════════════════════════════════════════════════════════════════════════

async def add_log_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await is_admin(ctx.bot, query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    folders = storage.get_folders()
    if not folders:
        await query.edit_message_text(
            "No folders exist. Create a folder first.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📁 New Folder", callback_data="add_folder"),
                 InlineKeyboardButton("⬅️ Back",       callback_data="main_menu")],
            ]),
        )
        return ConversationHandler.END

    buttons = [
        [InlineKeyboardButton(f"📁 {f['name']}", callback_data=f"pick_folder_{f['id']}")]
        for f in folders
    ]
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="main_menu")])
    await query.edit_message_text(
        "Pick a folder:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return AWAIT_LOG_FOLDER


async def pick_folder_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query     = update.callback_query
    await query.answer()
    folder_id = query.data.split("_", 2)[2]
    folder    = storage.get_folder(folder_id)
    ctx.user_data["log_folder_id"]   = folder_id
    ctx.user_data["log_folder_name"] = folder["name"]
    await query.edit_message_text("Send the log content:")
    return AWAIT_LOG_CONTENT


async def recv_log_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    content = update.message.text.strip()
    if not content:
        await update.message.reply_text("Content can't be empty. Send it again:")
        return AWAIT_LOG_CONTENT

    storage.add_coupon(ctx.user_data["log_folder_id"], content, "")
    adm = await is_admin(ctx.bot, update.effective_user.id)
    await update.message.reply_text(
        f"✅ Log saved to \"{ctx.user_data['log_folder_name']}\".",
        reply_markup=main_menu_keyboard(adm),
    )
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
#  ADMIN — DELETE LOG
# ════════════════════════════════════════════════════════════════════════════

async def delete_log_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await is_admin(ctx.bot, query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return
    await query.answer()

    logs = storage.get_all_coupons()
    if not logs:
        await query.edit_message_text(
            "No logs to delete.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]]
            ),
        )
        return

    buttons = [
        [InlineKeyboardButton(
            f"🗑 {c['code'][:40]}{'…' if len(c['code']) > 40 else ''}  ({c['folder_name']})",
            callback_data=f"dellog_{c['id']}"
        )]
        for c in logs
    ]
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="main_menu")])
    await query.edit_message_text(
        "Select log to delete:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def confirm_delete_log_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    log_id = query.data.split("_", 1)[1]
    storage.delete_coupon(log_id)
    adm = await is_admin(ctx.bot, query.from_user.id)
    await query.edit_message_text(
        "✅ Log deleted.",
        reply_markup=main_menu_keyboard(adm),
    )


# ════════════════════════════════════════════════════════════════════════════
#  ADMIN — DELETE FOLDER
# ════════════════════════════════════════════════════════════════════════════

async def delete_folder_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await is_admin(ctx.bot, query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return
    await query.answer()

    folders = storage.get_folders()
    if not folders:
        await query.edit_message_text(
            "No folders to delete.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]]
            ),
        )
        return

    buttons = [
        [InlineKeyboardButton(
            f"🗑 {f['name']}  ({f['coupon_count']} logs)",
            callback_data=f"delfolder_{f['id']}"
        )]
        for f in folders
    ]
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="main_menu")])
    await query.edit_message_text(
        "Select folder to delete (all logs inside will be removed):",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def confirm_delete_folder_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query     = update.callback_query
    await query.answer()
    folder_id = query.data.split("_", 1)[1]
    folder    = storage.get_folder(folder_id)
    storage.delete_folder(folder_id)
    adm = await is_admin(ctx.bot, query.from_user.id)
    await query.edit_message_text(
        f"✅ Folder \"{folder['name']}\" deleted.",
        reply_markup=main_menu_keyboard(adm),
    )


# ════════════════════════════════════════════════════════════════════════════
#  BROADCAST
# ════════════════════════════════════════════════════════════════════════════

def load_users() -> list[dict]:
    """Load users from users.json.

    Handles all common formats including your format:
      {"folders": {...}, "users": {"12345": {"user_id": 12345, ...}, ...}}
    Also handles users as a list of dicts or list of ints.
    """
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Unwrap top-level wrapper dict -> grab 'users' value
        if isinstance(data, dict):
            data = data.get("users", [])

        # data is now either a list or a dict-of-dicts (keyed by user_id string)
        if isinstance(data, dict):
            items = list(data.values())
        else:
            items = list(data)

        users = []
        for item in items:
            if isinstance(item, int):
                users.append({"id": item})
            elif isinstance(item, dict):
                # prefer explicit user_id field, fall back to id
                uid = item.get("user_id") or item.get("id")
                if uid:
                    users.append({"id": int(uid)})
        return users

    except FileNotFoundError:
        logger.warning("users.json not found at path: %s", USERS_FILE)
        return []
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Failed to load users.json: %s", e)
        return []


async def broadcast_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin presses the Broadcast button — ask for the message."""
    query = update.callback_query
    if not await is_admin(ctx.bot, query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    users = load_users()
    if not users:
        await query.edit_message_text(
            "⚠️ No users found in users.json. Make sure the file exists and is formatted correctly.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]]
            ),
        )
        return ConversationHandler.END

    await query.edit_message_text(
        f"📣 *Broadcast*\n\n"
        f"Found *{len(users)}* users in users.json.\n\n"
        f"Send the message you want to broadcast now.\n"
        f"Supports text, photos, videos, and documents — just send it directly.\n\n"
        f"Use /cancel to abort.",
        parse_mode="Markdown",
    )
    return AWAIT_BROADCAST_MSG


async def recv_broadcast_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Receive the broadcast message and send it to all users."""
    if not await is_admin(ctx.bot, update.effective_user.id):
        return ConversationHandler.END

    users = load_users()
    total   = len(users)
    success = 0
    failed  = 0
    blocked = 0

    # Send a progress message first
    progress_msg = await update.message.reply_text(
        f"📤 Sending to {total} users… please wait."
    )

    for user in users:
        uid = user["id"]
        try:
            # Forward the exact message the admin sent (preserves media, formatting)
            await update.message.copy(chat_id=uid)
            success += 1
        except Forbidden:
            # User blocked the bot
            blocked += 1
        except BadRequest as e:
            logger.warning("BadRequest for user %s: %s", uid, e)
            failed += 1
        except TelegramError as e:
            logger.warning("TelegramError for user %s: %s", uid, e)
            failed += 1

        # Small delay to respect Telegram rate limits (30 msg/sec max)
        await asyncio.sleep(0.05)

    adm = True  # we already checked above
    summary = (
        f"✅ Broadcast complete!\n\n"
        f"👥 Total users: {total}\n"
        f"✅ Delivered: {success}\n"
        f"🚫 Blocked bot: {blocked}\n"
        f"❌ Other errors: {failed}"
    )

    await progress_msg.edit_text(summary)
    await update.message.reply_text(
        "Back to menu:",
        reply_markup=main_menu_keyboard(adm),
    )
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
#  CANCEL
# ════════════════════════════════════════════════════════════════════════════

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    adm = await is_admin(ctx.bot, update.effective_user.id)
    await update.message.reply_text(
        "Cancelled.",
        reply_markup=main_menu_keyboard(adm),
    )
    return ConversationHandler.END


# ════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

def main():
    storage.init()

    app = Application.builder().token(BOT_TOKEN).build()

    folder_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_folder_cb, pattern="^add_folder$")],
        states={AWAIT_FOLDER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_folder_name)]},
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CallbackQueryHandler(main_menu_cb, pattern="^main_menu$")
        ],
        allow_reentry=True
    )

    log_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_log_cb, pattern="^add_log$")],
        states={
            AWAIT_LOG_FOLDER:  [CallbackQueryHandler(pick_folder_cb, pattern=r"^pick_folder_.+$")],
            AWAIT_LOG_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_log_content)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CallbackQueryHandler(main_menu_cb, pattern="^main_menu$")
        ],
        allow_reentry=True
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_cb, pattern="^broadcast$")],
        states={
            AWAIT_BROADCAST_MSG: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL)
                    & ~filters.COMMAND,
                    recv_broadcast_msg,
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CallbackQueryHandler(main_menu_cb, pattern="^main_menu$"),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(folder_conv)
    app.add_handler(log_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(CallbackQueryHandler(check_membership_cb,      pattern="^check_membership$"))
    app.add_handler(CallbackQueryHandler(main_menu_cb,             pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(browse_cb,                pattern="^browse$"))
    app.add_handler(CallbackQueryHandler(folder_cb,                pattern=r"^folder_.+$"))
    app.add_handler(CallbackQueryHandler(delete_log_cb,            pattern="^delete_log$"))
    app.add_handler(CallbackQueryHandler(confirm_delete_log_cb,    pattern=r"^dellog_.+$"))
    app.add_handler(CallbackQueryHandler(delete_folder_cb,         pattern="^delete_folder$"))
    app.add_handler(CallbackQueryHandler(confirm_delete_folder_cb, pattern=r"^delfolder_.+$"))

    logger.info("Bot is running…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
