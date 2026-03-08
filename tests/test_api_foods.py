"""Tests for GET/POST/PUT/DELETE /api/foods"""

import pytest


class TestListFoods:
    def test_empty(self, client):
        r = client.get("/api/foods")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_saved_food(self, client, sample_food):
        r = client.get("/api/foods")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == "chicken sandwich"
        assert data[0]["calories"] == 450

    def test_search_by_name(self, client, sample_food):
        r = client.get("/api/foods?search=chicken")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_search_no_results(self, client, sample_food):
        r = client.get("/api/foods?search=xyz")
        assert r.status_code == 200
        assert r.json() == []

    def test_search_matches_alias(self, client, sample_food):
        r = client.get("/api/foods?search=sarnie")
        assert r.status_code == 200
        assert len(r.json()) == 1


class TestGetFood:
    def test_get_existing(self, client, sample_food):
        r = client.get(f"/api/foods/{sample_food.id}")
        assert r.status_code == 200
        assert r.json()["name"] == "chicken sandwich"

    def test_get_nonexistent(self, client):
        r = client.get("/api/foods/999")
        assert r.status_code == 404


class TestCreateFood:
    def test_create_basic(self, client):
        r = client.post("/api/foods", json={"name": "banana", "calories": 90})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "banana"
        assert data["calories"] == 90
        assert "id" in data

    def test_name_normalised_lowercase(self, client):
        r = client.post("/api/foods", json={"name": "APPLE", "calories": 80})
        assert r.status_code == 201
        assert r.json()["name"] == "apple"

    def test_duplicate_returns_409(self, client, sample_food):
        r = client.post("/api/foods", json={"name": "chicken sandwich", "calories": 400})
        assert r.status_code == 409

    def test_create_with_macros(self, client):
        r = client.post("/api/foods", json={
            "name": "greek yogurt",
            "calories": 100,
            "protein_g": 10.0,
            "carbs_g": 8.0,
            "fat_g": 2.0,
            "unit": "100g",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["protein_g"] == 10.0
        assert data["unit"] == "100g"

    def test_create_missing_calories(self, client):
        r = client.post("/api/foods", json={"name": "mystery food"})
        assert r.status_code == 422  # validation error


class TestUpdateFood:
    def test_update_calories(self, client, sample_food):
        r = client.put(f"/api/foods/{sample_food.id}", json={"calories": 500})
        assert r.status_code == 200
        assert r.json()["calories"] == 500

    def test_update_nonexistent(self, client):
        r = client.put("/api/foods/999", json={"calories": 100})
        assert r.status_code == 404

    def test_partial_update(self, client, sample_food):
        r = client.put(f"/api/foods/{sample_food.id}", json={"aliases": "chick,sandwich"})
        assert r.status_code == 200
        data = r.json()
        assert data["aliases"] == "chick,sandwich"
        assert data["calories"] == 450  # unchanged


class TestDeleteFood:
    def test_delete_existing(self, client, sample_food):
        r = client.delete(f"/api/foods/{sample_food.id}")
        assert r.status_code == 204
        # Confirm gone
        r2 = client.get(f"/api/foods/{sample_food.id}")
        assert r2.status_code == 404

    def test_delete_nonexistent(self, client):
        r = client.delete("/api/foods/999")
        assert r.status_code == 404
