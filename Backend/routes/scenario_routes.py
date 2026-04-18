"""Scenario API routes."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify


def create_scenario_blueprint(scenario_service, logger: logging.Logger) -> Blueprint:
    bp = Blueprint("scenario_routes", __name__)

    @bp.get("/api/demo-scenario")
    def demo_scenario() -> tuple:
        try:
            result = scenario_service.get_demo_scenario()
            return jsonify(result), 200
        except Exception as exc:  # noqa: BLE001
            logger.exception("Demo scenario endpoint failed")
            return jsonify({"error": f"Failed to load demo scenario: {exc}"}), 500

    return bp
