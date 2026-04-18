"""Forecast API routes."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from models.schemas import ForecastRequest


def create_forecast_blueprint(forecast_service, logger: logging.Logger) -> Blueprint:
    bp = Blueprint("forecast_routes", __name__)

    @bp.post("/api/forecast")
    def forecast() -> tuple:
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify({"error": "Request body must be valid JSON."}), 400

        try:
            req = ForecastRequest.model_validate(payload)
        except ValidationError as exc:
            return jsonify({"error": f"Invalid forecast payload: {exc.errors()}"}), 400

        try:
            result = forecast_service.forecast(
                series_id=req.series_id,
                history=[p.model_dump(mode="json") for p in req.history],
                horizon_hours=req.horizon_hours,
            )
            return jsonify(result), 200
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            logger.exception("Forecast endpoint failed")
            return jsonify({"error": f"Forecast failed: {exc}"}), 500

    return bp
