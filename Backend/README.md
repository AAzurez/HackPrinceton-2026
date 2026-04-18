# GridShift DC Backend

Flask backend for forecasting + workload scheduling optimization.

## Run

```bash
cd Backend
pip install -r requirements.txt
python app.py
```

Server starts on `http://localhost:5000`.

## Endpoints

- `GET /health`
- `GET /api/demo-scenario`
- `POST /api/forecast`
- `POST /api/optimize`

## Model Path

Set model path via env var if needed:

```bash
set GRIDSHIFT_MODEL_DIR=C:\path\to\chronos2_finetuned
```

By default it tries:

1. `../Training/artifacts/chronos2_gridshift_full`
2. `Backend/models/chronos2_finetuned`

## Tests

```bash
cd Backend
pytest -q
```
