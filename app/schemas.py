from datetime import datetime
from pydantic import BaseModel, field_validator


# ── Foods ────────────────────────────────────────────────────────────────────

class FoodBase(BaseModel):
    name: str
    aliases: str | None = None
    calories: int
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    default_quantity: float = 1.0
    unit: str = "serving"

    @field_validator("name", mode="before")
    @classmethod
    def normalise_name(cls, v: str) -> str:
        return v.strip().lower()


class FoodCreate(FoodBase):
    pass


class FoodUpdate(BaseModel):
    name: str | None = None
    aliases: str | None = None
    calories: int | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    default_quantity: float | None = None
    unit: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalise_name(cls, v: str | None) -> str | None:
        return v.strip().lower() if v else None


class FoodRead(FoodBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Diary ────────────────────────────────────────────────────────────────────

class DiaryEntryBase(BaseModel):
    food_name: str
    quantity: float = 1.0
    calories: int
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    meal: str | None = None


class DiaryEntryCreate(DiaryEntryBase):
    food_id: int | None = None
    logged_at: datetime | None = None


class DiaryEntryRead(DiaryEntryBase):
    id: int
    food_id: int | None
    logged_at: datetime

    model_config = {"from_attributes": True}


# ── Summary ──────────────────────────────────────────────────────────────────

class MealSummary(BaseModel):
    meal: str | None
    calories: int
    entries: list[DiaryEntryRead]


class DailySummary(BaseModel):
    date: str
    total_calories: int
    total_protein_g: float | None
    total_carbs_g: float | None
    total_fat_g: float | None
    target_calories: int
    meals: list[MealSummary]


class WeeklyDay(BaseModel):
    date: str
    total_calories: int
    entry_count: int
