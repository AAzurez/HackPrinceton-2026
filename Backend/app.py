"""Flask app entrypoint for GridShift DC backend."""

from __future__ import annotations

from flask import Flask, jsonify
from flask_cors import CORS

from config import AppConfig
from routes.forecast_routes import create_forecast_blueprint
from routes.optimize_routes import create_optimize_blueprint
from routes.scenario_routes import create_scenario_blueprint
from services.explanation_service import ExplanationService
from services.forecast_service import ForecastService
from services.optimization_service import OptimizationService
from services.scenario_service import ScenarioService
from utils.logger import get_logger


def create_app() -> Flask:
    """Application factory for tests and local runtime."""
    config = AppConfig.from_env()
    logger = get_logger("gridshift.backend", config.log_level)

    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    app.config["GRIDSHIFT_CONFIG"] = config

    # CORS for local frontend development.
    CORS(app, resources={r"/api/*": {"origins": "*"}, r"/health": {"origins": "*"}})

    # Services are initialized once at startup.
    forecast_service = ForecastService(config=config, logger=logger)
    scenario_service = ScenarioService(config=config, logger=logger)
    explanation_service = ExplanationService(logger=logger)
    optimization_service = OptimizationService(logger=logger, explanation_service=explanation_service)

    app.config["SERVICES"] = {
        "forecast": forecast_service,
        "scenario": scenario_service,
        "optimization": optimization_service,
    }

    app.register_blueprint(create_forecast_blueprint(forecast_service, logger))
    app.register_blueprint(create_optimize_blueprint(optimization_service, logger))
    app.register_blueprint(create_scenario_blueprint(scenario_service, logger))

    @app.get("/health")
    def health() -> tuple:
        return (
            jsonify(
                {
                    "status": "ok",
                    "model_loaded": bool(forecast_service.model_loaded),
                    "model_dir": str(config.model_dir),
                }
            ),
            200,
        )

    @app.get("/")
    def root() -> tuple:
        return jsonify({"service": config.app_name, "status": "running"}), 200

    return app


app = create_app()


if __name__ == "__main__":
    cfg: AppConfig = app.config["GRIDSHIFT_CONFIG"]
    app.run(host=cfg.host, port=cfg.port, debug=cfg.debug)
