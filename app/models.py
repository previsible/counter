from datetime import datetime, date, timezone
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, Text, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Food(Base):
    __tablename__ = "foods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    calories: Mapped[int] = mapped_column(Integer, nullable=False)
    protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    default_quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unit: Mapped[str] = mapped_column(String, default="serving")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    diary_entries: Mapped[list["DiaryEntry"]] = relationship("DiaryEntry", back_populates="food")

    def alias_list(self) -> list[str]:
        if not self.aliases:
            return []
        return [a.strip() for a in self.aliases.split(",") if a.strip()]


class DiaryEntry(Base):
    __tablename__ = "diary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    food_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("foods.id"), nullable=True)
    food_name: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    calories: Mapped[int] = mapped_column(Integer, nullable=False)
    protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    meal: Mapped[str | None] = mapped_column(String, nullable=True)

    food: Mapped["Food | None"] = relationship("Food", back_populates="diary_entries")


class Exercise(Base):
    __tablename__ = "exercise"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)  # "steps" or "exercise"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calories_burned: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
