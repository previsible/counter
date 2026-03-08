from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models import Food
from app.schemas import FoodCreate, FoodUpdate, FoodRead

router = APIRouter(prefix="/api/foods", tags=["foods"])


@router.get("", response_model=list[FoodRead])
def list_foods(
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    q = db.query(Food)
    if search:
        term = f"%{search.lower()}%"
        q = q.filter(
            or_(
                Food.name.ilike(term),
                Food.aliases.ilike(term),
            )
        )
    return q.order_by(Food.name).all()


@router.get("/{food_id}", response_model=FoodRead)
def get_food(food_id: int, db: Session = Depends(get_db)):
    food = db.get(Food, food_id)
    if not food:
        raise HTTPException(status_code=404, detail="Food not found")
    return food


@router.post("", response_model=FoodRead, status_code=201)
def create_food(payload: FoodCreate, db: Session = Depends(get_db)):
    existing = db.query(Food).filter(Food.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Food '{payload.name}' already exists")
    food = Food(**payload.model_dump())
    db.add(food)
    db.commit()
    db.refresh(food)
    return food


@router.put("/{food_id}", response_model=FoodRead)
def update_food(food_id: int, payload: FoodUpdate, db: Session = Depends(get_db)):
    food = db.get(Food, food_id)
    if not food:
        raise HTTPException(status_code=404, detail="Food not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(food, field, value)
    db.commit()
    db.refresh(food)
    return food


@router.delete("/{food_id}", status_code=204)
def delete_food(food_id: int, db: Session = Depends(get_db)):
    food = db.get(Food, food_id)
    if not food:
        raise HTTPException(status_code=404, detail="Food not found")
    db.delete(food)
    db.commit()
