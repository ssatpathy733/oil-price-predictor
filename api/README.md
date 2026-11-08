# Brent Scenario API

Middle layer between the trained model (`package/`) and the frontend.

## Run it (from the repo root)

```bash
pip install -r api/requirements.txt
uvicorn api.main:app --reload --port 8000
```

Open http://localhost:8000/docs to try every endpoint in the browser.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Is the server up? |
| GET | `/spec` | Slider names, labels, ranges, defaults, eras. Build the sliders from this. |
| GET | `/history?days=250` | Past Brent/DXY/VIX/GPR for the chart's history line |
| GET | `/events` | 35 past events + what happened afterwards (for the chatbot) |
| POST | `/forecast` | Slider values in, 20-day p10/p50/p90 fan + contributions out |
| GET | `/forecast?dxy_pct=2&vix_pct=40` | Same, query params, for quick browser tests |

Bad input (unknown era, spot without sigma30, ...) returns HTTP 422 with the model's error message.

## Calling it from the frontend

```js
const API = "http://localhost:8000";

const spec = await (await fetch(`${API}/spec`)).json();       // build sliders from spec.inputs
const past = await (await fetch(`${API}/history?days=60`)).json();

const res = await fetch(`${API}/forecast`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ dxy_pct: 2, vix_pct: 40, gpr_pct: 50, era: "all" }),
});
const result = await res.json();
// result.path -> 21 points {day, date, p10, p50, p90} for the fan chart
// result.summary, result.contributions, result.warnings -> text/bars to show
```

## Chatbot hook (later)

The chatbot's job is to turn "OPEC cuts production" into `{dxy_pct, vix_pct, gpr_pct}`.
Give it `/events` as examples of what actually followed past events, clamp its answers to
the `hard_min`/`hard_max` in `/spec`, then POST the result to `/forecast`.
