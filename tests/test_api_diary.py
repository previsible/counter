"""Tests for diary API endpoints."""

from datetime import datetime, timezone, timedelta
import pytest


def _log(client, food_name="banana", calories=90, meal=None, food_id=None):
    payload = {
        "food_name": food_name,
        "calories": calories,
        "quantity": 1.0,
    }
    if meal:
        payload["meal"] = meal
    if food_id:
        payload["food_id"] = food_id
    r = client.post("/api/diary", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


class TestGetDiary:
    def test_empty_today(self, client):
        r = client.get("/api/diary")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_todays_entry(self, client):
        _log(client, "apple", 80)
        r = client.get("/api/diary")
        data = r.json()
        assert len(data) == 1
        assert data[0]["food_name"] == "apple"

    def test_date_filter(self, client):
        # Log entry with a past date via the API
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        r = client.post("/api/diary", json={
            "food_name": "old food",
            "calories": 100,
            "quantity": 1.0,
            "logged_at": past,
        })
        assert r.status_code == 201

        # Today's diary should be empty
        r2 = client.get("/api/diary")
        assert r2.status_code == 200
        assert r2.json() == []

    def test_specific_date_returns_entries(self, client):
        two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
        date_str = two_days_ago.date().isoformat()
        past_iso = two_days_ago.isoformat()

        client.post("/api/diary", json={
            "food_name": "old food",
            "calories": 100,
            "quantity": 1.0,
            "logged_at": past_iso,
        })

        r = client.get(f"/api/diary?date={date_str}")
        assert r.status_code == 200
        assert len(r.json()) == 1


class TestDiaryRange:
    def test_range_includes_both_endpoints(self, client):
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)

        _log(client, "today food", 100)
        client.post("/api/diary", json={
            "food_name": "yesterday food",
            "calories": 200,
            "quantity": 1.0,
            "logged_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        })

        r = client.get(f"/api/diary/range?start={yesterday}&end={today}")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_range_excludes_outside(self, client):
        _log(client, "today", 100)
        yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        two_days_ago = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()

        r = client.get(f"/api/diary/range?start={two_days_ago}&end={yesterday}")
        assert r.status_code == 200
        assert r.json() == []


class TestDiarySummary:
    def test_empty_summary(self, client):
        r = client.get("/api/diary/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["total_calories"] == 0
        assert data["meals"] == []

    def test_summary_totals(self, client):
        _log(client, "eggs", 150, meal="breakfast")
        _log(client, "sandwich", 400, meal="lunch")

        r = client.get("/api/diary/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["total_calories"] == 550
        assert len(data["meals"]) == 2

    def test_summary_by_meal(self, client):
        _log(client, "porridge", 300, meal="breakfast")
        _log(client, "coffee", 50, meal="breakfast")
        _log(client, "salad", 200, meal="lunch")

        r = client.get("/api/diary/summary")
        data = r.json()
        meal_map = {m["meal"]: m for m in data["meals"]}

        assert meal_map["breakfast"]["calories"] == 350
        assert len(meal_map["breakfast"]["entries"]) == 2
        assert meal_map["lunch"]["calories"] == 200

    def test_summary_target_calories_in_response(self, client):
        r = client.get("/api/diary/summary")
        data = r.json()
        assert "target_calories" in data
        assert data["target_calories"] > 0


class TestWeekly:
    def test_weekly_returns_7_days(self, client):
        r = client.get("/api/diary/weekly")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 7

    def test_weekly_today_reflects_entry(self, client):
        _log(client, "banana", 90)
        r = client.get("/api/diary/weekly")
        today_entry = r.json()[-1]  # last is today
        assert today_entry["total_calories"] == 90
        assert today_entry["entry_count"] == 1

    def test_weekly_empty_days_are_zero(self, client):
        r = client.get("/api/diary/weekly")
        data = r.json()
        for day in data[:-1]:  # all days except today
            assert day["total_calories"] == 0


class TestLogEntry:
    def test_log_basic(self, client, sample_food):
        r = client.post("/api/diary", json={
            "food_name": "chicken sandwich",
            "calories": 450,
            "quantity": 1.0,
            "food_id": sample_food.id,
        })
        assert r.status_code == 201
        data = r.json()
        assert data["food_name"] == "chicken sandwich"
        assert data["calories"] == 450
        assert data["food_id"] == sample_food.id

    def test_log_without_food_id(self, client):
        r = client.post("/api/diary", json={
            "food_name": "mystery snack",
            "calories": 200,
            "quantity": 1.0,
        })
        assert r.status_code == 201
        assert r.json()["food_id"] is None

    def test_log_with_meal(self, client):
        r = client.post("/api/diary", json={
            "food_name": "toast",
            "calories": 120,
            "quantity": 2.0,
            "meal": "breakfast",
        })
        assert r.status_code == 201
        assert r.json()["meal"] == "breakfast"

    def test_log_missing_required_field(self, client):
        r = client.post("/api/diary", json={"food_name": "toast"})
        assert r.status_code == 422


class TestDeleteEntry:
    def test_delete_existing(self, client):
        entry = _log(client, "apple", 80)
        r = client.delete(f"/api/diary/{entry['id']}")
        assert r.status_code == 204

        # Gone from today's diary
        r2 = client.get("/api/diary")
        assert r2.json() == []

    def test_delete_nonexistent(self, client):
        r = client.delete("/api/diary/999")
        assert r.status_code == 404
