# Calorie Tracker Bot

A self-hosted calorie tracking system with a Telegram bot interface and REST API. Learns your eating habits by building a personal food database — no external calorie APIs required.

## Features

- **Telegram bot** — log food in natural language, e.g. `lunch: chicken salad and a roll`
- **Personal food database** — every new food you log is saved and recognised next time
- **Fuzzy matching** — finds foods even with slight variations in spelling or wording
- **REST API** — clean JSON API ready for a frontend dashboard
- **Daily & weekly summaries** — `/today`, `/week` commands

## Quick Start

### 1. Clone & install dependencies

```bash
git clone <your-repo>
cd calorie-bot
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and set TELEGRAM_BOT_TOKEN
```

Get a bot token from [@BotFather](https://t.me/BotFather) on Telegram.

### 3. Run

```bash
uvicorn app.main:app --reload
```

The FastAPI server starts on `http://localhost:8000` and the Telegram bot starts automatically in the background.

## Bot Usage

### Logging food

Just send a message:

```
2 eggs on toast
chicken sandwich
coffee with milk, banana
lunch: chicken salad and a bread roll
```

- Items separated by commas, "and", or newlines are logged individually
- Prefix with a meal name: `breakfast:`, `lunch:`, `dinner:`, `snack:`
- Quantities like `2`, `2x`, `half`, `a` are detected automatically
- **Known foods** are confirmed immediately: ✅ Chicken sandwich — 450 kcal
- **New foods** prompt you for the calorie count, then saved for next time

### Quick correction

If you logged the wrong calories, just say:
```
no that was 300
```
or
```
actually 350
```

### Commands

| Command | Description |
|---------|-------------|
| `/today` | Today's diary with meal breakdown and total |
| `/week` | Daily calorie totals for the last 7 days |
| `/foods` | List all saved foods (paginated) |
| `/edit <food> <calories>` | Update a food's calorie count |
| `/delete_last` or `/undo` | Remove the most recent diary entry |
| `/help` | Show this help |

## REST API

Base URL: `http://localhost:8000`

### Foods

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/foods` | List all foods (optional `?search=`) |
| `GET` | `/api/foods/{id}` | Get a single food |
| `POST` | `/api/foods` | Create a food |
| `PUT` | `/api/foods/{id}` | Update a food |
| `DELETE` | `/api/foods/{id}` | Delete a food |

### Diary

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/diary?date=YYYY-MM-DD` | Entries for a date (default: today) |
| `GET` | `/api/diary/range?start=...&end=...` | Entries for a date range |
| `GET` | `/api/diary/summary?date=YYYY-MM-DD` | Daily summary with meal breakdown |
| `GET` | `/api/diary/weekly` | Last 7 days daily totals |
| `POST` | `/api/diary` | Log an entry |
| `DELETE` | `/api/diary/{id}` | Delete an entry |

Interactive API docs: `http://localhost:8000/docs`

## Project Structure

```
app/
├── main.py          # FastAPI app + startup + bot background task
├── config.py        # Settings from environment variables
├── database.py      # SQLAlchemy setup
├── models.py        # ORM models (foods, diary)
├── schemas.py       # Pydantic request/response schemas
├── routers/
│   ├── foods.py     # Food CRUD endpoints
│   └── diary.py     # Diary endpoints
└── bot/
    ├── bot.py       # Telegram bot handlers
    ├── parser.py    # Natural language parsing
    └── matcher.py   # Food database matching
```

## Design Principles

- **Learn fast** — every logged food is saved immediately
- **Low friction** — message in, log out in seconds
- **Offline-first** — no external calorie APIs; you own your data
- **Extensible** — clean REST API for future dashboard
