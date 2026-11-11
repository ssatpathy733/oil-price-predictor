"""
HTTP API for the Brent 20-day scenario model (the "middle layer").

    frontend  --HTTP/JSON-->  this file  --Python calls-->  package/oil_model

Run from the repo root:
    pip install -r api/requirements.txt
    uvicorn api.main:app --reload --port 8000

Then open http://localhost:8000/docs for interactive docs (Swagger UI).
"""
import sys
import warnings
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import os
from pydantic import BaseModel
from google import genai
from google.genai import types
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

# The model package lives in <repo>/package (oil_model/ and artifacts/ side by side).
PACKAGE_DIR = Path(__file__).resolve().parent.parent / "package"
sys.path.insert(0, str(PACKAGE_DIR))

from oil_model import event_analogs, feature_spec, forecast, history  # noqa: E402

app = FastAPI(
    title="Brent Scenario API",
    description="Wraps oil_model.forecast() so the frontend and chatbot can run what-if scenarios.",
    version="0.1.0",
)

# Allow the frontend (any dev server) to call us from the browser.
# Before deploying, replace "*" with your real frontend URL(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Era = Literal["all", "2010-2019", "2021-2026"]

load_dotenv()

# client = genai.Client()
client = genai.Client(vertexai=True)

class PricePoint(BaseModel):
    date: str = Field(..., examples=["2026-03-12"])
    brent: float

class ForecastRequest(BaseModel):
    """Scenario inputs are % changes over the next 20 trading days. All fields are optional."""

    dxy_pct: float = Field(0.0, description="US dollar index % change (slider -5..5)")
    vix_pct: float = Field(0.0, description="VIX % change (slider -43..116)")
    gpr_pct: float = Field(0.0, description="Geopolitical Risk index % change (slider -34..67)")
    era: Era = "all"

    # Starting point: pass at most ONE of these options (see package/README.md).
    spot: Optional[float] = Field(None, description="Brent price in USD; requires sigma30")
    sigma30: Optional[float] = Field(None, description="30-day daily volatility as a fraction, e.g. 0.021")
    date: Optional[str] = Field(None, description="Date of spot/sigma30 (YYYY-MM-DD); only with spot+sigma30")
    as_of: Optional[str] = Field(None, description="Past start date (YYYY-MM-DD), 2010-02-17 or later")
    prices: Optional[List[PricePoint]] = Field(None, description="At least 31 recent daily Brent closes")

class AskRequest(BaseModel):
    question: str
    dxy_pct: float
    vix_pct: float
    gpr_pct: float
    era: str
    spot: float | None = None
    p50: float | None = None

class AskResponse(BaseModel):
    intro: str
    evidence_dates: List[str] = Field(default_factory=list)

def run_forecast(req: ForecastRequest) -> dict:
    """Call the model, turning bad input into a clean 422 instead of a 500."""
    kwargs = req.model_dump(exclude_none=True)  # prices become plain {"date","brent"} dicts
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            result = forecast(**kwargs)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    # Clamping notes already come back in result["warnings"]; add any Python-level ones too.
    extra = [str(w.message) for w in caught if str(w.message) not in result.get("warnings", [])]
    if extra:
        result["warnings"] = list(result.get("warnings", [])) + extra
    return result


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/spec")
def get_spec():
    """Slider names, labels, ranges, defaults, current levels and the era list. Build the UI from this."""
    return feature_spec()


@app.get("/history")
def get_history(
    days: int = Query(250, ge=1, le=5000),
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to 2026-03-12"),
):
    """Past daily Brent / DXY / VIX / GPR for the chart's history line."""
    try:
        return history(days=days, as_of=as_of)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/events")
def get_events():
    """35 past events and what Brent/DXY/VIX/GPR did after them. Use this to ground the chatbot."""
    return event_analogs()


@app.post("/forecast")
def post_forecast(req: ForecastRequest):
    """Main endpoint: send slider values, get the 20-day p10/p50/p90 fan back."""
    return run_forecast(req)


@app.get("/forecast")
def get_forecast(
    dxy_pct: float = 0.0,
    vix_pct: float = 0.0,
    gpr_pct: float = 0.0,
    era: Era = "all",
):
    """Same as POST but with query params, handy for testing in a browser address bar."""
    return run_forecast(ForecastRequest(dxy_pct=dxy_pct, vix_pct=vix_pct, gpr_pct=gpr_pct, era=era))

@app.post("/ask")
def ask_event(req: AskRequest):
    slider_specs = {item["name"]: item for item in feature_spec()["inputs"]}
    historical_events = event_analogs()
    compact_events = [
        {
            "date": event["date"],
            "event_type": event["event_type"],
            "description": event["description"],
            "severity": event["severity"],
            "brent_20d_pct": event["brent_20d_pct"],
            "dxy_20d_pct": event["dxy_20d_pct"],
            "vix_20d_pct": event["vix_20d_pct"],
            "gpr_20d_pct": event["gpr_20d_pct"],
            "model_check": event["model_check"],
        }
        for event in historical_events
    ]
    system_prompt = (
        f"You are an energy market analyst embedded in a Brent crude scenario dashboard. "
        f"Current dashboard state: Spot price ${req.spot}, 20-day middle estimate ${req.p50}, "
        f"Sliders: DXY {req.dxy_pct:+.1f}%, VIX {req.vix_pct:+.1f}%, GPR {req.gpr_pct:+.1f}%, "
        f"Historical regime: '{req.era}'. "
        f"Write a brief 1-2 sentence plain-text introduction explaining the event's possible "
        f"market context. Do not use Markdown, bullets, slider names, or slider actions in the "
        f"introduction; the application will display the calculated slider actions as bullets. "
        f"Do not propose numerical slider changes. Select up to "
        f"three meaningfully relevant historical "
        f"analogs by listing their exact dates in evidence_dates. Do not generate slider values; "
        f"the application calculates those from the selected events' observed 20-day changes. "
        f"If the event is too vague or no analog is meaningfully relevant, use an empty "
        f"evidence_dates list. Do not describe an analog as proof of causation or state uncertain "
        f"market relationships as facts. Historical outcomes are examples, not guaranteed predictions. "
        f"Historical analogs (20-trading-day observed changes): "
        f"{json.dumps(compact_events, separators=(',', ':'))}"
    )

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=req.question,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=AskResponse,
        ),
    )
    try:
        parsed = response.parsed
        if parsed is None:
            parsed = AskResponse.model_validate_json(response.text)
        elif isinstance(parsed, AskResponse):
            parsed = parsed.model_dump()
        else:
            parsed = AskResponse.model_validate(parsed).model_dump()
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="The assistant returned an invalid scenario.") from exc

    known_events = {event["date"]: event for event in historical_events}
    evidence = []
    for date in parsed.pop("evidence_dates", []):
        event = known_events.get(date)
        if event and all(item["date"] != date for item in evidence):
            evidence.append({
                "date": event["date"],
                "description": event["description"],
                "event_type": event["event_type"],
                "brent_20d_pct": event["brent_20d_pct"],
                "dxy_20d_pct": event["dxy_20d_pct"],
                "vix_20d_pct": event["vix_20d_pct"],
                "gpr_20d_pct": event["gpr_20d_pct"],
                "model_check": event["model_check"],
            })
        if len(evidence) == 3:
            break
    parsed["evidence"] = evidence
    if evidence:
        # Proposed slider moves are the mean observed 20-day changes across cited analogs.
        suggestion = {}
        calculations = []
        for name, item in slider_specs.items():
            factor = name.removesuffix("_pct")
            observed_key = f"{factor}_20d_pct"
            observed_values = [float(event[observed_key]) for event in evidence]
            mean_observed = sum(observed_values) / len(observed_values)
            low, high, step = item["slider_min"], item["slider_max"], item["step"]
            clipped_value = min(high, max(low, mean_observed))
            snapped_value = low + round((clipped_value - low) / step) * step
            slider_value = round(min(high, max(low, snapped_value)), 4)
            suggestion[name] = slider_value
            calculations.append({
                "name": name,
                "label": item["label"],
                "observations": [
                    {"date": event["date"], "value": round(value, 2)}
                    for event, value in zip(evidence, observed_values)
                ],
                "mean_observed": round(mean_observed, 2),
                "slider_value": slider_value,
                "clipped": abs(clipped_value - mean_observed) > 1e-9,
                "rounded_to_step": abs(snapped_value - clipped_value) > 1e-9,
                "step": step,
            })
        parsed["suggested_sliders"] = suggestion
        parsed["suggestion_calculations"] = calculations
    else:
        parsed["suggested_sliders"] = None
        parsed["suggestion_calculations"] = []

    return parsed

@app.get("/")
async def serve_index():
    return FileResponse("index.html")
