from datetime import datetime, date, timezone, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Exercise, DiaryEntry, utcnow
from app.schemas import ExerciseCreate, ExerciseUpdate, ExerciseRead, DayBalance

router = APIRouter(prefix="/api/exercise", tags=["exercise"])
balance_router = APIRouter(prefix="/api/balance", tags=["balance"])

settings = get_settings()


def _local_today() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def _utc_day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def get_balance_for_date(d: date, db: Session) -> DayBalance:
    start, end = _utc_day_bounds(d)
    food_calories = sum(
        e.calories for e in db.query(DiaryEntry)
        .filter(DiaryEntry.logged_at >= start, DiaryEntry.logged_at < end)
        .all()
    )

    exercise_entries = db.query(Exercise).filter(Exercise.date == d).all()
    steps_entry = next((e for e in exercise_entries if e.type == "steps"), None)
    steps = steps_entry.steps or 0 if steps_entry else 0
    steps_cal = steps_entry.calories_burned if steps_entry else 0
    exercise_cal = sum(e.calories_burned for e in exercise_entries if e.type == "exercise")
    total_burned = steps_cal + exercise_cal

    return DayBalance(
        date=d.isoformat(),
        food_calories=food_calories,
        steps=steps,
        steps_calories_burned=steps_cal,
        exercise_calories_burned=exercise_cal,
        total_burned=total_burned,
        net_balance=food_calories - total_burned,
        target=settings.daily_calorie_target,
    )


# ── Exercise CRUD ─────────────────────────────────────────────────────────────

@router.get("", response_model=list[ExerciseRead])
def get_exercise(
    date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    target = date or _local_today()
    return (
        db.query(Exercise)
        .filter(Exercise.date == target)
        .order_by(Exercise.logged_at)
        .all()
    )


@router.post("", response_model=ExerciseRead, status_code=201)
def log_exercise(payload: ExerciseCreate, db: Session = Depends(get_db)):
    target_date = payload.date or _local_today()

    if payload.type == "steps":
        existing = (
            db.query(Exercise)
            .filter(Exercise.date == target_date, Exercise.type == "steps")
            .first()
        )
        if existing:
            existing.steps = payload.steps
            existing.calories_burned = payload.calories_burned
            if payload.description:
                existing.description = payload.description
            existing.updated_at = utcnow()
            db.commit()
            db.refresh(existing)
            return existing

    entry = Exercise(
        type=payload.type,
        description=payload.description,
        steps=payload.steps,
        calories_burned=payload.calories_burned,
        date=target_date,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{exercise_id}", response_model=ExerciseRead)
def update_exercise(exercise_id: int, payload: ExerciseUpdate, db: Session = Depends(get_db)):
    entry = db.get(Exercise, exercise_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Exercise entry not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(entry, field, value)
    entry.updated_at = utcnow()
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{exercise_id}", status_code=204)
def delete_exercise(exercise_id: int, db: Session = Depends(get_db)):
    entry = db.get(Exercise, exercise_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Exercise entry not found")
    db.delete(entry)
    db.commit()


# ── Balance ───────────────────────────────────────────────────────────────────

@balance_router.get("", response_model=DayBalance)
def get_balance(
    date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    target = date or _local_today()
    return get_balance_for_date(target, db)


@balance_router.get("/weekly", response_model=list[DayBalance])
def get_balance_weekly(db: Session = Depends(get_db)):
    today = _local_today()
    return [
        get_balance_for_date(today - timedelta(days=i), db)
        for i in range(6, -1, -1)
    ]
