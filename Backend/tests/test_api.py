"""Basic API smoke tests for GridShift backend."""

from __future__ import annotations

import pytest

from app import create_app


@pytest.fixture()
def client():
    app = create_app()
    app.config.update({"TESTING": True})
    with app.test_client() as test_client:
        yield test_client


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "ok"
    assert "model_loaded" in payload


def test_demo_scenario(client):
    resp = client.get("/api/demo-scenario")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert "profile" in payload
    assert "workloads" in payload
    assert len(payload["profile"]) == 24
    assert len(payload["workloads"]) >= 1


def test_optimize_with_demo_data(client):
    demo = client.get("/api/demo-scenario").get_json()
    resp = client.post("/api/optimize", json=demo)
    assert resp.status_code == 200

    payload = resp.get_json()
    assert "baseline_profile" in payload
    assert "optimized_profile" in payload
    assert "schedule_changes" in payload
    assert "metrics" in payload
    assert "summary" in payload

    assert len(payload["baseline_profile"]) == 24
    assert len(payload["optimized_profile"]) == 24
