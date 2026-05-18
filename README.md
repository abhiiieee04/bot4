# 🎟 Coupon Bot — Railway Volume Storage

A Telegram bot that drops exclusive coupon codes to community members.
Users must join your **private channel** and **private group** before accessing codes.
All data is stored in a JSON file on a **Railway Volume** — no database needed.

---

## ✨ Features

| Feature | Details |
|---|---|
| 🔐 Private membership gate | Verifies users are in your private channel AND group |
| 🗂 Folder system | Organize coupons by brand, date, or any category |
| 💾 Railway Volume storage | JSON file on persistent disk — survives restarts & redeploys |
| 👮 Admin-only management | Only channel/group admins can add or delete |
| 📅 Date-stamped folders | Creation date shown next to each folder automatically |
| 🗑 One-tap delete | Delete individual coupons or entire folders |

---

## 🚀 Deploy to Railway

### Step 1 — Create your Telegram Bot
1. Open Telegram → search `@BotFather`
2. Send `/newbot` and follow the prompts → copy the **bot token**
3. Send `/setprivacy` → select your bot → set to **Disable**
   _(This lets the bot check group membership)_

### Step 2 — Add the bot as Admin
- Add the bot to your **private channel** as an Admin
- Add the bot to your **private group** as an Admin
- The bot needs "Add Members" permission so it can call getChatMember

### Step 3 — Get your Chat IDs
Add `@userinfobot` to both your channel and group.
It will reply with the numeric ID (e.g. `-1001234567890`).

### Step 4 — Get your private invite links
- **Channel**: open channel → Info → Invite Links → Create New Link → copy `https://t.me/+xxxx`
- **Group**: open group → Info → Invite Links → Create New Link → copy `https://t.me/+xxxx`
- Use links with **no expiry and no member limit**

### Step 5 — Push to GitHub

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/coupon-bot.git
git push -u origin main
```

### Step 6 — Create Railway project
1. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**
2. Select your repo

### Step 7 — Add a Volume ⬅️ critical step
1. In your Railway service → click **+ Add Volume**
2. Set **Mount Path** to `/data`
3. Click **Add** — Railway provisions persistent disk attached to your service

### Step 8 — Set environment variables
Go to your service → **Variables** tab → add:

```
BOT_TOKEN       = your_token_from_botfather
CHANNEL_ID      = -1001234567890
GROUP_ID        = -1009876543210
CHANNEL_INVITE  = https://t.me/+xxxxxxxxxxxxxx
GROUP_INVITE    = https://t.me/+yyyyyyyyyyyyyy
```

No DATABASE_URL needed — storage is entirely on the Volume at `/data/coupons.json`.

### Step 9 — Deploy
Railway auto-deploys. Check **Logs** and confirm:
```
Storage ready at /data/coupons.json
Bot is running…
```

---

## 🗂 How data is stored

Everything lives in a single JSON file `/data/coupons.json` on the Volume:

```json
{
  "folders": {
    "abc123": {
      "id": "abc123",
      "name": "Nike June 2025",
      "created_at": "2025-06-01T10:00:00",
      "coupons": {
        "xyz789": {
          "id": "xyz789",
          "code": "NIKE20",
          "description": "20% off everything",
          "created_at": "2025-06-01T10:05:00"
        }
      }
    }
  }
}
```

- Writes use an **atomic rename** (write `.tmp` → rename) so the file is never corrupted mid-write
- A **thread lock** prevents race conditions from concurrent users
- Data persists through Railway restarts, redeploys, and service updates
- To back up: download `/data/coupons.json` from Railway's Volume browser

---

## 📱 Commands

| Command | Who |
|---|---|
| `/start` | Everyone |
| `/cancel` | Cancels any in-progress admin action |
| `/skip` | Skip optional description when adding a coupon |

---

## 👮 Admin Workflow

Admins are auto-detected — anyone who is admin/creator in the channel or group gets the admin buttons.

1. `/start` → extra admin buttons appear
2. **📁 New Folder** → type a name → saved instantly
3. **➕ Add Coupon** → pick folder → type code → optional description
4. **🗑 Delete Coupon** → pick from list → deleted
5. **🗂 Delete Folder** → deletes folder + all coupons inside

---

## 👤 User Workflow

1. Send `/start`
2. Not a member → sees join buttons (your private invite links)
3. Joins → taps **✅ I've Joined** → re-checked
4. Verified → browses folders → taps folder → sees all codes

---

## 🏗 Project Structure

```
coupon-bot/
├── bot.py           # All bot logic and handlers
├── storage.py       # JSON file storage on Railway Volume
├── requirements.txt # python-telegram-bot only — no database driver
├── Procfile
├── railway.toml
├── .env.example
└── .gitignore
```

---

## 💻 Local Development

```bash
pip install -r requirements.txt
mkdir -p /tmp/coupon-data
cp .env.example .env
# edit .env with real values
STORAGE_PATH=/tmp/coupon-data $(cat .env | xargs) python bot.py
```
