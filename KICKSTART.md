# Kickstart Guide — Telegram Bot Store (aiogram3)

A Telegram bot for a pizza restaurant with product catalog, shopping cart, order placement, and admin panel. Built with **aiogram 3**, **SQLAlchemy 2 (async)**, and **aiohttp**.

---

## Prerequisites

- **Python 3.10+**
- **pip** (Python package manager)
- A **Telegram account** to create a bot

---

## 1. API Keys & External Services

### Telegram Bot Token (required)

You need a bot token from Telegram's BotFather:

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts (choose a name and username)
3. BotFather will reply with a token like: `7123456789:AAH...`
4. Save this token — it goes in your `.env` file as `TOKEN`

### Database URL (required)

The bot uses SQLAlchemy async and supports:

| Database   | URL format                                      | Extra driver       |
|------------|------------------------------------------------|--------------------|
| **SQLite** (easiest) | `sqlite+aiosqlite:///bot_base.db`              | included in deps   |
| **PostgreSQL**       | `postgresql+asyncpg://user:pass@host:5432/db`  | included in deps   |

For local development, SQLite is the simplest — no server needed.

### No other API keys required

Payment and delivery options exist in the UI but are **not integrated** with real services. No Stripe, no delivery APIs — just informational pages.

---

## 2. Setup Steps

```bash
# Clone the repo
git clone https://github.com/modemobpsycho/aiogram3-tg-bot-store.git
cd aiogram3-tg-bot-store

# Create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## 3. Configure Environment

Create a `.env` file inside the `telegrambot/` directory:

```bash
cp telegrambot/.env.example telegrambot/.env
```

Edit `telegrambot/.env`:

```env
TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DB_URL=sqlite+aiosqlite:///bot_base.db
```

| Variable | What it is | Where to get it |
|----------|-----------|-----------------|
| `TOKEN`  | Telegram Bot API token | @BotFather on Telegram |
| `DB_URL` | SQLAlchemy async connection string | Choose SQLite for local dev |

---

## 4. Run the Bot

```bash
cd telegrambot
python main.py
```

The bot will:
1. Drop and recreate all database tables (dev behavior — resets on every restart)
2. Seed initial categories ("Еда" / Food, "Напитки" / Drinks) and banner descriptions
3. Start polling for Telegram updates

---

## 5. First-Time Usage

### As a regular user
- Open your bot in Telegram and send `/start`
- You'll see the main menu with: Products, Cart, About, Payment, Delivery
- Browse products by category, add to cart, place orders

### Setting up admins
- **Add the bot to a Telegram group**
- A group admin sends `/admin` in the group chat
- This populates the bot's admin list from the group's actual admins
- Now those users can send `/admin` in a **private chat** with the bot to access the admin panel

### As an admin (private chat)
- Send `/admin` to the bot
- Options: Add product, Edit product, Delete product, Upload banner images
- When adding a product: provide name → description → select category → price → upload image

---

## 6. Bot Commands

| Command     | Where       | What it does                    |
|-------------|-------------|--------------------------------|
| `/start`    | Private     | Show main menu                 |
| `/menu`     | Private     | Browse product catalog         |
| `/about`    | Private     | About the restaurant           |
| `/payment`  | Private     | Payment options info           |
| `/shipping` | Private     | Delivery/pickup info           |
| `/admin`    | Private     | Open admin panel (admins only) |
| `/admin`    | Group       | Populate admin list from group |

---

## 7. Project Structure (key files)

```
telegrambot/
├── main.py                    # Entry point — bot init, routers, startup
├── .env                       # Your config (TOKEN, DB_URL)
├── database/
│   ├── models.py              # DB tables: User, Product, Category, Cart, Banner
│   ├── engine.py              # Async SQLAlchemy engine setup
│   └── orm_query.py           # All CRUD operations
├── handlers/
│   ├── user_private.py        # User commands and menu callbacks
│   ├── admin_private.py       # Admin product/banner management (FSM)
│   ├── user_group.py          # Group moderation & admin detection
│   └── menu_processing.py     # Menu content rendering logic
├── keyboards/
│   ├── inline.py              # Inline keyboard builders
│   └── reply.py               # Reply keyboard builder
├── filters/
│   └── chat_types.py          # ChatTypeFilter, IsAdmin filter
├── middlewares/
│   └── db.py                  # Injects DB session into handlers
├── common/
│   ├── texts_for_db.py        # Seed data (categories, banner text)
│   ├── bot_cmds_list.py       # Command definitions
│   └── restricted_words.py    # Moderation word list
└── utils/
    └── paginator.py           # Pagination for products & cart
```

---

## 8. Database Schema

Five tables, auto-created on startup:

- **User** — Telegram user info (user_id, name, phone)
- **Category** — Product categories (seeded: Food, Drinks)
- **Product** — Items with name, description, price, image, category FK
- **Cart** — Per-user cart items with quantity
- **Banner** — Page banners (main, about, payment, shipping, catalog, cart)

Product images are stored as Telegram `file_id` strings — no external file storage needed.

---

## 9. Important Notes

- **Database resets on every restart** — `drop_db()` is called in `on_startup`. Remove this call in `main.py` for production use.
- **Primary language is Russian** — UI strings are mostly in Russian. English localization exists but is minimal.
- **No real payment processing** — payment/delivery pages are informational stubs.
- **No Docker setup** — run directly with Python.
- **SQL echo is ON** — all queries are logged to console (`echo=True` in `engine.py`). Disable for production.

---

## Quick Checklist

- [ ] Python 3.10+ installed
- [ ] Bot token from @BotFather
- [ ] `.env` file created in `telegrambot/` with `TOKEN` and `DB_URL`
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Run `python telegrambot/main.py`
- [ ] Send `/start` to your bot in Telegram
- [ ] Add bot to a group and run `/admin` to set up admin access
