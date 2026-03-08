import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import foods, diary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

_bot_task: asyncio.Task | None = None


async def _run_bot():
    """Run the Telegram bot with polling in a background task."""
    from app.config import get_settings
    settings = get_settings()

    if not settings.telegram_bot_token:
        log.warning("TELEGRAM_BOT_TOKEN not set — bot will not start")
        return

    from app.bot.bot import build_application
    application = build_application()

    log.info("Starting Telegram bot...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    log.info("Telegram bot is running")

    # Keep alive until cancelled
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        log.info("Stopping Telegram bot...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bot_task
    # Initialise database
    init_db()
    log.info("Database initialised")

    # Start bot in background
    _bot_task = asyncio.create_task(_run_bot())

    yield

    # Shutdown
    if _bot_task and not _bot_task.done():
        _bot_task.cancel()
        try:
            await _bot_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Calorie Tracker API",
    description="Personal calorie tracking with Telegram bot interface",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(foods.router)
app.include_router(diary.router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Must be mounted last so API routes take priority
app.mount("/", StaticFiles(directory="static", html=True), name="static")
