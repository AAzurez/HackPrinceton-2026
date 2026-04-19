# GridShift Frontend

React + Tailwind dashboard for GridShift.

## Run locally

Start backend first:

```bash
cd Backend
python app.py
```

Then start frontend:

```bash
cd Frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Build

```bash
npm run build
npm run preview
```

## Notes

- Frontend calls:
  - `GET /health`
  - `GET /api/demo-scenario`
  - `POST /api/optimize`
- Default backend URL is `http://localhost:5000`.
- Override API base with:
  - Windows PowerShell: `$env:VITE_API_BASE_URL="http://localhost:5000"`
- Main UI entry: `src/App.jsx`.
- Reusable components are in `src/components/`.
