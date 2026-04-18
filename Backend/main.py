"""Compatibility runner for IDE launch configs."""

from app import app


if __name__ == "__main__":
    config = app.config["GRIDSHIFT_CONFIG"]
    app.run(host=config.host, port=config.port, debug=config.debug)
