"""
Telegram bot: handlers for food logging, commands, and conversation flows.

Conversation state machine
--------------------------
User sends food text
  └─► handle_message()
        ├─ known food  → show confirm keyboard → AWAIT_CONFIRM
        └─ unknown food → ask calories         → AWAIT_CALORIES

AWAIT_CONFIRM (inline-keyboard callback)
  handle_callback()
    ├─ Yes   → log, next item
    ├─ Edit  → ask calories → AWAIT_CALORIES
    └─ Skip  → next item
           next item cycles back through AWAIT_CONFIRM / AWAIT_CALORIES
           until all items done → END

AWAIT_CALORIES (plain text)
  handle_calories_input()
    → save food (if new), log entry, next item
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from app.config import get_settings
from app.database import SessionLocal
from app.models import Food, DiaryEntry
from app.bot.parser import parse_message, ParsedItem
from app.bot.matcher import find_match

log = logging.getLogger(__name__)
settings = get_settings()
LOCAL_TZ = ZoneInfo(settings.timezone)

# ── Conversation states ───────────────────────────────────────────────────────
AWAIT_CONFIRM, AWAIT_CALORIES = range(2)

# ── user_data keys ────────────────────────────────────────────────────────────
K_PENDING      = "pending_items"    # list[dict]
K_IDX          = "current_index"    # int
K_LOGGED       = "logged_entries"   # list[dict]
K_EDITING      = "editing_index"    # int | None — set when user clicks Edit
K_LAST_ENTRY   = "last_entry_id"    # int — for quick corrections


# ── Time helpers ──────────────────────────────────────────────────────────────

def _now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def _today_bounds_utc() -> tuple[datetime, datetime]:
    d = _now_local().date()
    start = datetime(d.year, d.month, d.day, tzinfo=LOCAL_TZ).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def _daily_total(db) -> int:
    start, end = _today_bounds_utc()
    rows = db.query(DiaryEntry).filter(
        DiaryEntry.logged_at >= start, DiaryEntry.logged_at < end
    ).all()
    return sum(r.calories for r in rows)


# ── Formatting ────────────────────────────────────────────────────────────────

def _fmt_entry(e: DiaryEntry) -> str:
    qty = f" ×{e.quantity}" if e.quantity != 1.0 else ""
    meal = f" ({e.meal})" if e.meal else ""
    return f"• {e.food_name.title()}{qty}{meal} — {e.calories} kcal"


def _confirm_keyboard(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Yes",  callback_data=f"yes:{idx}"),
        InlineKeyboardButton("✏️ Edit", callback_data=f"edit:{idx}"),
        InlineKeyboardButton("⏭️ Skip", callback_data=f"skip:{idx}"),
    ]])


# ── Pending-state helpers ─────────────────────────────────────────────────────

def _reset(ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data[K_PENDING]    = []
    ctx.user_data[K_IDX]        = 0
    ctx.user_data[K_LOGGED]     = []
    ctx.user_data.pop(K_EDITING, None)


def _pending(ctx: ContextTypes.DEFAULT_TYPE) -> list[dict]:
    return ctx.user_data.setdefault(K_PENDING, [])


def _idx(ctx: ContextTypes.DEFAULT_TYPE) -> int:
    return ctx.user_data.get(K_IDX, 0)


def _advance(ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data[K_IDX] = _idx(ctx) + 1


# ── DB helpers ────────────────────────────────────────────────────────────────

def _log_entry(db, food: Food | None, item: ParsedItem, calories: int) -> DiaryEntry:
    def scale(val):
        return val * item.quantity if val is not None else None

    entry = DiaryEntry(
        food_id=food.id if food else None,
        food_name=item.name,
        quantity=item.quantity,
        calories=calories,
        protein_g=scale(food.protein_g) if food else None,
        carbs_g=scale(food.carbs_g) if food else None,
        fat_g=scale(food.fat_g) if food else None,
        meal=item.meal,
        logged_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ── Core: process the next pending item ───────────────────────────────────────

async def _next_item(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show a confirm keyboard (known food) or ask for calories (unknown food).
    Returns the appropriate ConversationHandler state, or END when done.
    """
    pending = _pending(ctx)
    i = _idx(ctx)

    if i >= len(pending):
        await _summary(update, ctx)
        _reset(ctx)
        return ConversationHandler.END

    item_data = pending[i]
    item: ParsedItem = item_data["item"]
    food: Food | None = item_data.get("food")

    # Reply target works for both messages and callback queries
    reply_target = (
        update.effective_message
        if update.effective_message
        else update.callback_query.message
    )

    if food:
        calories = round(food.calories * item.quantity)
        qty_str = f"{item.quantity} × " if item.quantity != 1.0 else ""
        text = (
            f"✅ *{item.name.title()}*\n"
            f"{qty_str}{food.calories} kcal each = *{calories} kcal*\n"
            f"Log it?"
        )
        await reply_target.reply_text(text, parse_mode="Markdown", reply_markup=_confirm_keyboard(i))
        return AWAIT_CONFIRM
    else:
        await reply_target.reply_text(
            f"🆕 I don't know *{item.name.title()}* yet.\n"
            f"How many calories per serving?",
            parse_mode="Markdown",
        )
        return AWAIT_CALORIES


async def _summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    logged: list[dict] = ctx.user_data.get(K_LOGGED, [])
    reply_target = update.effective_message or update.callback_query.message

    if not logged:
        await reply_target.reply_text("Nothing logged.")
        return

    lines = ["📊 *Logged:*"]
    for e in logged:
        qty = f" ×{e['quantity']}" if e["quantity"] != 1.0 else ""
        lines.append(f"  • {e['food_name'].title()}{qty} — {e['calories']} kcal")

    with SessionLocal() as db:
        total = _daily_total(db)

    target = settings.daily_calorie_target
    remaining = target - total
    lines.append(f"\n*Daily total: {total} / {target} kcal*")
    if remaining > 0:
        lines.append(f"_{remaining} kcal remaining today_")
    else:
        lines.append(f"_Over target by {abs(remaining)} kcal_")

    await reply_target.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Entry point ───────────────────────────────────────────────────────────────

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    # Quick correction: "no that was 300" / "actually 350" / "correction: 280"
    m = re.match(
        r"^(?:no[,.]?\s+)?(?:that was|it was|actually|correction[:]?)\s+(\d+)",
        text, re.IGNORECASE,
    )
    if m:
        return await _apply_correction(update, ctx, int(m.group(1)))

    items = parse_message(text)
    if not items:
        await update.message.reply_text(
            "I couldn't parse that. Try something like 'chicken sandwich' or '2 eggs'."
        )
        return ConversationHandler.END

    _reset(ctx)

    with SessionLocal() as db:
        pending = [{"item": item, "food": find_match(item.name, db)} for item in items]

    ctx.user_data[K_PENDING] = pending
    return await _next_item(update, ctx)


async def _apply_correction(update: Update, ctx: ContextTypes.DEFAULT_TYPE, new_cal: int) -> int:
    last_id = ctx.user_data.get(K_LAST_ENTRY)
    if not last_id:
        await update.message.reply_text("No recent entry to correct.")
        return ConversationHandler.END

    with SessionLocal() as db:
        entry = db.get(DiaryEntry, last_id)
        if not entry:
            await update.message.reply_text("Couldn't find that entry.")
            return ConversationHandler.END
        old_cal = entry.calories
        entry.calories = new_cal
        db.commit()
        total = _daily_total(db)
        name = entry.food_name

    await update.message.reply_text(
        f"✏️ *{name.title()}*: {old_cal} → {new_cal} kcal\nDaily total: {total} kcal",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ── AWAIT_CONFIRM: inline-keyboard callbacks ──────────────────────────────────

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    action, idx_str = query.data.split(":", 1)
    i = int(idx_str)
    pending = _pending(ctx)

    if i >= len(pending):
        await query.edit_message_text("Session expired — please re-send your message.")
        return ConversationHandler.END

    item_data = pending[i]
    item: ParsedItem = item_data["item"]
    food: Food | None = item_data.get("food")

    if action == "yes":
        calories = round(food.calories * item.quantity)
        with SessionLocal() as db:
            entry = _log_entry(db, food, item, calories)
            entry_id = entry.id

        ctx.user_data[K_LAST_ENTRY] = entry_id
        ctx.user_data.setdefault(K_LOGGED, []).append(
            {"food_name": item.name, "quantity": item.quantity, "calories": calories}
        )
        await query.edit_message_text(f"✅ Logged: {item.name.title()} — {calories} kcal")
        _advance(ctx)
        return await _next_item(update, ctx)

    elif action == "edit":
        await query.edit_message_text(
            f"✏️ How many calories for *{item.name.title()}*"
            f"{f' (×{item.quantity})' if item.quantity != 1.0 else ''}?",
            parse_mode="Markdown",
        )
        ctx.user_data[K_EDITING] = i
        return AWAIT_CALORIES

    elif action == "skip":
        await query.edit_message_text(f"⏭️ Skipped {item.name.title()}")
        _advance(ctx)
        return await _next_item(update, ctx)

    return ConversationHandler.END


# ── AWAIT_CALORIES: user types a number ──────────────────────────────────────

async def handle_calories_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    match = re.search(r"\d+", text)
    if not match:
        await update.message.reply_text("Please enter a number, e.g. '450'")
        return AWAIT_CALORIES

    calories_per_serving = int(match.group())
    editing_i = ctx.user_data.pop(K_EDITING, None)
    i = editing_i if editing_i is not None else _idx(ctx)

    pending = _pending(ctx)
    if i >= len(pending):
        await update.message.reply_text("Session expired — please re-send your message.")
        return ConversationHandler.END

    item_data = pending[i]
    item: ParsedItem = item_data["item"]
    existing_food: Food | None = item_data.get("food")
    total_calories = round(calories_per_serving * item.quantity)

    with SessionLocal() as db:
        if existing_food is None:
            food = Food(name=item.name, calories=calories_per_serving)
            db.add(food)
            db.flush()
            entry = _log_entry(db, food, item, total_calories)
            await update.message.reply_text(
                f"✅ Saved *{item.name.title()}* ({calories_per_serving} kcal/serving)"
                f" and logged {total_calories} kcal.",
                parse_mode="Markdown",
            )
        else:
            entry = _log_entry(db, existing_food, item, total_calories)
            await update.message.reply_text(
                f"✅ Logged {item.name.title()} — {total_calories} kcal"
            )
        entry_id = entry.id

    ctx.user_data[K_LAST_ENTRY] = entry_id
    ctx.user_data.setdefault(K_LOGGED, []).append(
        {"food_name": item.name, "quantity": item.quantity, "calories": total_calories}
    )

    # Advance past the item we just handled
    ctx.user_data[K_IDX] = i
    _advance(ctx)
    return await _next_item(update, ctx)


# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    with SessionLocal() as db:
        start, end = _today_bounds_utc()
        entries = (
            db.query(DiaryEntry)
            .filter(DiaryEntry.logged_at >= start, DiaryEntry.logged_at < end)
            .order_by(DiaryEntry.logged_at)
            .all()
        )

        if not entries:
            await update.message.reply_text("Nothing logged today yet.")
            return

        by_meal: dict[str | None, list[DiaryEntry]] = defaultdict(list)
        for e in entries:
            by_meal[e.meal].append(e)

        lines = [f"📊 *Today — {_now_local().strftime('%a %d %b')}*\n"]
        ordered_meals = ["breakfast", "brunch", "lunch", "dinner", "supper", "snack"]

        for meal in ordered_meals:
            if meal in by_meal:
                meal_total = sum(e.calories for e in by_meal[meal])
                lines.append(f"*{meal.title()}* ({meal_total} kcal)")
                lines.extend(_fmt_entry(e) for e in by_meal[meal])
                lines.append("")

        # Any unlisted meal labels
        for meal, meal_entries in by_meal.items():
            if meal not in ordered_meals and meal is not None:
                meal_total = sum(e.calories for e in meal_entries)
                lines.append(f"*{meal.title()}* ({meal_total} kcal)")
                lines.extend(_fmt_entry(e) for e in meal_entries)
                lines.append("")

        # Untagged entries
        if None in by_meal:
            meal_total = sum(e.calories for e in by_meal[None])
            lines.append(f"*Other* ({meal_total} kcal)")
            lines.extend(_fmt_entry(e) for e in by_meal[None])
            lines.append("")

        total = sum(e.calories for e in entries)
        target = settings.daily_calorie_target
        lines.append(f"*Total: {total} / {target} kcal*")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = [f"📊 *Last 7 days*\n"]
    with SessionLocal() as db:
        today = _now_local().date()
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            start = datetime(d.year, d.month, d.day, tzinfo=LOCAL_TZ).astimezone(timezone.utc)
            end = start + timedelta(days=1)
            entries = db.query(DiaryEntry).filter(
                DiaryEntry.logged_at >= start, DiaryEntry.logged_at < end
            ).all()
            total = sum(e.calories for e in entries)
            bar = "█" * max(1, total // 200) if total else "·"
            label = "Today" if i == 0 else d.strftime("%a %d %b")
            lines.append(f"`{label:<12}` {total:>5} kcal  {bar}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_foods(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    with SessionLocal() as db:
        foods = db.query(Food).order_by(Food.name).all()

    if not foods:
        await update.message.reply_text("No foods saved yet. Log something to get started!")
        return

    PAGE = 20
    try:
        page = int(ctx.args[0]) if ctx.args else 1
    except (ValueError, IndexError):
        page = 1

    total_pages = (len(foods) + PAGE - 1) // PAGE
    page = max(1, min(page, total_pages))
    chunk = foods[(page - 1) * PAGE : page * PAGE]

    lines = [f"🍽️ *Foods ({page}/{total_pages})*\n"]
    for f in chunk:
        lines.append(f"• {f.name.title()} — {f.calories} kcal/{f.unit or 'serving'}")
    if total_pages > 1:
        lines.append(f"\n_/foods {page + 1} for next page_")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text(
            "Usage: /edit <food name> <calories>\nExample: /edit banana 90"
        )
        return

    *name_parts, cal_str = ctx.args
    food_name = " ".join(name_parts).lower()

    try:
        new_cal = int(cal_str)
    except ValueError:
        await update.message.reply_text("Calories must be a whole number.")
        return

    with SessionLocal() as db:
        food = db.query(Food).filter(Food.name == food_name).first()
        if not food:
            food = db.query(Food).filter(Food.name.ilike(f"%{food_name}%")).first()
        if not food:
            await update.message.reply_text(f"Food '{food_name}' not found. Check /foods.")
            return
        old_cal = food.calories
        food.calories = new_cal
        db.commit()
        name = food.name

    await update.message.reply_text(
        f"✏️ *{name.title()}*: {old_cal} → {new_cal} kcal/serving",
        parse_mode="Markdown",
    )


async def cmd_delete_last(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    with SessionLocal() as db:
        entry = (
            db.query(DiaryEntry)
            .order_by(DiaryEntry.logged_at.desc())
            .first()
        )
        if not entry:
            await update.message.reply_text("Nothing to delete.")
            return
        name, cal = entry.food_name, entry.calories
        db.delete(entry)
        db.commit()
        total = _daily_total(db)

    await update.message.reply_text(
        f"🗑️ Removed *{name.title()}* ({cal} kcal)\nDaily total: {total} kcal",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Calorie Tracker*\n\n"
        "*Log food* — just send a message:\n"
        "  `2 eggs on toast`\n"
        "  `lunch: chicken salad, bread roll`\n"
        "  `coffee with milk, banana`\n\n"
        "*Commands:*\n"
        "  /today — today's diary & total\n"
        "  /week — last 7 days\n"
        "  /foods — saved foods list\n"
        "  /edit <food> <cals> — update calories\n"
        "  /undo or /delete\\_last — remove last entry\n"
        "  /help — this message\n\n"
        "*Quick correction:* after logging say\n"
        "  `no that was 300`",
        parse_mode="Markdown",
    )


# ── Application factory ───────────────────────────────────────────────────────

def build_application() -> Application:
    token = settings.telegram_bot_token
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
        ],
        states={
            AWAIT_CONFIRM: [
                CallbackQueryHandler(handle_callback),
            ],
            AWAIT_CALORIES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_calories_input),
            ],
        },
        fallbacks=[
            CommandHandler("help", cmd_help),
            CommandHandler("today", cmd_today),
            CommandHandler("week", cmd_week),
            CommandHandler("undo", cmd_delete_last),
            CommandHandler("delete_last", cmd_delete_last),
        ],
        allow_reentry=True,
        per_chat=True,
        per_user=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("foods", cmd_foods))
    app.add_handler(CommandHandler("edit", cmd_edit))
    app.add_handler(CommandHandler("delete_last", cmd_delete_last))
    app.add_handler(CommandHandler("undo", cmd_delete_last))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))

    return app
