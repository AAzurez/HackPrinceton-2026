"""Optimization API routes."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from models.schemas import OptimizeRequest


def create_optimize_blueprint(optimization_service, logger: logging.Logger) -> Blueprint:
    bp = Blueprint("optimize_routes", __name__)

    @bp.post("/api/optimize")
    def optimize() -> tuple:
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify({"error": "Request body must be valid JSON."}), 400

        try:
            req = OptimizeRequest.model_validate(payload)
        except ValidationError as exc:
            return jsonify({"error": f"Invalid workload payload: {exc.errors()}"}), 400

        try:
            result = optimization_service.optimize(
                profile=[p.model_dump(mode="json") for p in req.profile],
                workloads=[w.model_dump(mode="json") for w in req.workloads],
            )
            return jsonify(result), 200
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            logger.exception("Optimize endpoint failed")
            return jsonify({"error": f"Optimization failed: {exc}"}), 500

    return bp
