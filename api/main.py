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
