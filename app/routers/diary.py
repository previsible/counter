from datetime import datetime, date, timezone, timedelta
from collections import defaultdict
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import DiaryEntry, Exercise
from app.schemas import (
    DiaryEntryCreate, DiaryEntryRead,
    DailySummary, MealSummary,
    WeeklyDay, ExerciseRead,
)

router = APIRouter(prefix="/api/diary", tags=["diary"])
settings = get_settings()


def _local_today() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def _start_end_of_day_utc(d: date) -> tuple[datetime, datetime]:
    start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def _build_summary(entries: list[DiaryEntry], target_date: date, db: Session) -> DailySummary:
    total_cal = sum(e.calories for e in entries)
    total_protein = sum(e.protein_g for e in entries if e.protein_g is not None) or None
    total_carbs = sum(e.carbs_g for e in entries if e.carbs_g is not None) or None
    total_fat = sum(e.fat_g for e in entries if e.fat_g is not None) or None

    by_meal: dict[str | None, list[DiaryEntry]] = defaultdict(list)
    for e in entries:
        by_meal[e.meal].append(e)

    meals = [
        MealSummary(
            meal=meal,
            calories=sum(e.calories for e in meal_entries),
            entries=[DiaryEntryRead.model_validate(e) for e in meal_entries],
        )
        for meal, meal_entries in sorted(
            by_meal.items(), key=lambda x: (x[0] is None, x[0])
        )
    ]

    exercise_entries = db.query(Exercise).filter(Exercise.date == target_date).all()
    steps_entry = next((e for e in exercise_entries if e.type == "steps"), None)
    steps = steps_entry.steps or 0 if steps_entry else 0
    steps_cal = steps_entry.calories_burned if steps_entry else 0
    exercise_cal = sum(e.calories_burned for e in exercise_entries if e.type == "exercise")
    total_burned = steps_cal + exercise_cal

    return DailySummary(
        date=target_date.isoformat(),
        total_calories=total_cal,
        total_protein_g=total_protein,
        total_carbs_g=total_carbs,
        total_fat_g=total_fat,
        target_calories=settings.daily_calorie_target,
        meals=meals,
        steps=steps,
        steps_calories_burned=steps_cal,
        exercise_calories_burned=exercise_cal,
        total_burned=total_burned,
        net_balance=total_cal - total_burned,
        exercise_entries=[ExerciseRead.model_validate(e) for e in exercise_entries],
    )


@router.get("", response_model=list[DiaryEntryRead])
def get_diary(
    date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    target = date or _local_today()
    start, end = _start_end_of_day_utc(target)
    return (
        db.query(DiaryEntry)
        .filter(DiaryEntry.logged_at >= start, DiaryEntry.logged_at < end)
        .order_by(DiaryEntry.logged_at)
        .all()
    )


@router.get("/range", response_model=list[DiaryEntryRead])
def get_diary_range(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
):
    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    end_dt = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)
    return (
        db.query(DiaryEntry)
        .filter(DiaryEntry.logged_at >= start_dt, DiaryEntry.logged_at < end_dt)
        .order_by(DiaryEntry.logged_at)
        .all()
    )


@router.get("/summary", response_model=DailySummary)
def get_summary(
    date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    target = date or _local_today()
    start, end = _start_end_of_day_utc(target)
    entries = (
        db.query(DiaryEntry)
        .filter(DiaryEntry.logged_at >= start, DiaryEntry.logged_at < end)
        .order_by(DiaryEntry.logged_at)
        .all()
    )
    return _build_summary(entries, target, db)


@router.get("/weekly", response_model=list[WeeklyDay])
def get_weekly(db: Session = Depends(get_db)):
    today = _local_today()
    results = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        start, end = _start_end_of_day_utc(d)
        entries = (
            db.query(DiaryEntry)
            .filter(DiaryEntry.logged_at >= start, DiaryEntry.logged_at < end)
            .all()
        )
        exercise_entries = db.query(Exercise).filter(Exercise.date == d).all()
        steps_entry = next((e for e in exercise_entries if e.type == "steps"), None)
        steps_cal = steps_entry.calories_burned if steps_entry else 0
        exercise_cal = sum(e.calories_burned for e in exercise_entries if e.type == "exercise")
        total_burned = steps_cal + exercise_cal
        total_calories = sum(e.calories for e in entries)
        results.append(
            WeeklyDay(
                date=d.isoformat(),
                total_calories=total_calories,
                entry_count=len(entries),
                net_balance=total_calories - total_burned,
                total_burned=total_burned,
                steps_calories_burned=steps_cal,
                exercise_calories_burned=exercise_cal,
            )
        )
    return results


@router.post("", response_model=DiaryEntryRead, status_code=201)
def log_entry(payload: DiaryEntryCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    logged_at = data.pop("logged_at", None) or datetime.now(timezone.utc)
    entry = DiaryEntry(**data, logged_at=logged_at)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(DiaryEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Diary entry not found")
    db.delete(entry)
    db.commit()
