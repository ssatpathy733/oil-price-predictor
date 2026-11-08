"""Public API for the API/UI teams. Needs only numpy, pandas and the JSON files in artifacts/."""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.holiday import (AbstractHolidayCalendar, GoodFriday, Holiday, USLaborDay,
                                    USMartinLutherKingJr, USMemorialDay, USPresidentsDay,
                                    USThanksgivingDay, nearest_workday)
from pandas.tseries.offsets import CustomBusinessDay

ARTIFACTS = Path(__file__).resolve().parent.parent / "artifacts"
INPUTS = ("dxy", "vix", "gpr")


class _ExchangeHolidays(AbstractHolidayCalendar):
    """US exchange holidays (the dataset follows the US trading calendar)."""
    rules = [Holiday("New Year", month=1, day=1, observance=nearest_workday), USMartinLutherKingJr,
             USPresidentsDay, GoodFriday, USMemorialDay,
             Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
             Holiday("Independence Day", month=7, day=4, observance=nearest_workday), USLaborDay,
             USThanksgivingDay, Holiday("Christmas", month=12, day=25, observance=nearest_workday)]


@lru_cache(maxsize=None)
def _load(name):
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _path_dates(start, n):
    cal = CustomBusinessDay(calendar=_ExchangeHolidays())
    return tuple(str(d.date()) for d in pd.date_range(pd.Timestamp(start), periods=n, freq=cal))


def feature_spec():
    """Slider definitions: names, labels, ranges, defaults, current levels, era list."""
    return _load("feature_spec.json")


def event_analogs():
    """The 35 timeline events with the DXY/VIX/GPR/Brent changes that followed each (5 and 20 days)."""
    return _load("event_analogs.json")


@lru_cache(maxsize=None)
def _history():
    return pd.read_csv(ARTIFACTS / "history.csv")


def history(days=250, as_of=None):
    """`days` trading days of Brent, DXY, VIX and GPR up to `as_of` (default: end of data)."""
    h = _history()
    if as_of is not None:
        h = h[h["date"] <= str(pd.Timestamp(as_of).date())]
    return h.drop(columns="sigma30").tail(days).to_dict(orient="records")


SIGMA30_MAX = 0.2  # daily fraction; 2010–2026 peaked near 0.09, so anything above is annualised or in %


def _anchor(as_of, prices, spot, sigma30, date, H):
    """Start point of the fan: (date, price, sigma30, next H dates, actual prices on those dates)."""
    if spot is not None:
        if not spot > 0:
            raise ValueError("spot must be a positive Brent price in USD")
        if not 0 < sigma30 <= SIGMA30_MAX:
            raise ValueError(f"sigma30={sigma30} is not a daily fraction (expected roughly 0.005–0.09; "
                             f"max accepted {SIGMA30_MAX}). Divide annualised volatility by sqrt(252) "
                             "and percentages by 100.")
        date = str(pd.Timestamp(date if date is not None else pd.Timestamp.today()).date())
        return date, float(spot), float(sigma30), list(_path_dates(date, H + 1)[1:]), {}
    if prices is not None:
        p = pd.DataFrame(prices).sort_values("date")
        if len(p) < 31:
            raise ValueError("prices needs at least 31 daily closes (30 returns) to estimate volatility")
        sigma = float(p["brent"].pct_change().tail(30).std())
        date, brent = str(pd.Timestamp(p["date"].iloc[-1]).date()), float(p["brent"].iloc[-1])
        return date, brent, sigma, list(_path_dates(date, H + 1)[1:]), {}
    h = _history()
    i = len(h) - 1
    if as_of is not None:
        i = int(h["date"].searchsorted(str(pd.Timestamp(as_of).date()), side="right")) - 1
        if i < 0:
            raise ValueError(f"as_of must be on or after {h['date'].iloc[0]}")
    row = h.iloc[i]
    after = h.iloc[i + 1:i + 1 + H]  # real trading days where the data has them, calendar after that
    dates = list(after["date"])
    if len(dates) < H:
        dates += list(_path_dates(dates[-1] if dates else row["date"], H - len(dates) + 1)[1:])
    return row["date"], float(row["brent"]), float(row["sigma30"]), dates, dict(zip(after["date"], after["brent"]))


def forecast(dxy_pct=0.0, vix_pct=0.0, gpr_pct=0.0, era="all", as_of=None, prices=None,
             spot=None, sigma30=None, date=None):
    """Brent price range for a hypothetical 20-trading-day scenario.

    Conditional and educational: "if these things happen, what range is plausible based on
    2010–2026 history". Not a forecast of what oil will do. With all scenario inputs at 0
    (the baseline), the median equals the starting price.

    Parameters
    ----------
    Scenario: percent changes over the next 20 trading days. Slider range is the 1st–99th
    percentile of history; values beyond the clamp range are clamped, with a warning.

    dxy_pct : float, default 0.0
        Change in the US dollar index, e.g. 3 = DXY ends 3% higher. Slider -5..5, clamp -8..8.
    vix_pct : float, default 0.0
        Change in the VIX. Moves the median and also widens (rise) or narrows (fall) the
        interval. Slider -43..116, clamp -57..505.
    gpr_pct : float, default 0.0
        Change in the Geopolitical Risk index. Has almost no effect on the median (no reliable
        historical relationship). Slider -34..67, clamp -41..203.
    era : {"all", "2010-2019", "2021-2026"}, default "all"
        Which period's fitted relationships to apply. The DXY effect is negative before 2020
        and positive (but not significant) after 2021.

    Starting point (pass at most one; default is the last day of the data, 2026-03-12).
    Only the starting price and volatility change; the fitted relationships stay 2010–2026.

    as_of : str or date-like, optional
        Start from this historical date, from 2010-02-17 onward. A non-trading day rolls back
        to the previous trading day; a date after the data ends uses the last day. Path points
        then include "actual", the real Brent close that followed, where the data has it.
    prices : list of {"date": "YYYY-MM-DD", "brent": float}, optional
        Your own recent daily closes (e.g. a live feed), at least 31, in any order. The fan
        starts from the latest close; sigma30 is computed from the last 30 daily returns.
    spot : float, optional
        Today's Brent price in USD. Requires sigma30.
    sigma30 : float, optional
        Brent's 30-day volatility: std of the last 30 daily simple returns (including today),
        as a daily fraction, e.g. 0.021. Not percent (2.1) and not annualized (0.33; divide
        by sqrt(252)). Must be in (0, 0.2]; outside 0.0058–0.0886 (2010–2026) adds a warning.
        Requires spot.
    date : str or date-like, optional
        Date of spot/sigma30; the path starts on the next US trading day. Defaults to today.
        Only valid with spot and sigma30.

    Returns
    -------
    dict (JSON-serialisable)
        as_of              start date (YYYY-MM-DD)
        spot, sigma30      starting price (USD) and daily volatility used
        anchor_source      "history", "prices" or "spot"
        era, era_label     era key and display name
        horizon_days       20
        inputs_requested   {"dxy", "vix", "gpr"} as passed, in %
        inputs_used        the same after clamping
        summary            {"p10", "p50", "p90"} USD at day 20, and "median_change_pct"
        path               21 points (day 0 = start, then 20 trading days, US exchange
                           calendar): {"day", "date", "p10", "p50", "p90"[, "actual"]}
        contributions      per input: {"log_change", "pct", "usd"}; "usd" sums to p50 - spot
        warnings           list of strings to show the user (clamping, unreliable effects,
                           unusual sigma30, start after the training data)
        disclaimer         text to show alongside the result

    Raises
    ------
    ValueError
        Unknown era; as_of before 2010-02-17; fewer than 31 prices; spot without sigma30 or
        vice versa; date without spot; spot <= 0; sigma30 outside (0, 0.2]; or more than one
        starting-point option.
    """
    model, spec = _load("model.json"), feature_spec()
    if era not in model["eras"]:
        raise ValueError(f"era must be one of {list(model['eras'])}")
    if (spot is None) != (sigma30 is None):
        raise ValueError("spot and sigma30 must be given together")
    if date is not None and spot is None:
        raise ValueError("date is only used with spot and sigma30")
    if sum(x is not None for x in (as_of, prices, spot)) > 1:
        raise ValueError("pass at most one of as_of, prices, or spot + sigma30")
    e, H = model["eras"][era], model["horizon_days"]
    source = "prices" if prices is not None else "spot" if spot is not None else "history"
    start, price, vol, dates, actual = _anchor(as_of, prices, spot, sigma30, date, H)
    a = {"date": start, "brent": price, "sigma30": vol}
    requested = {"dxy": float(dxy_pct), "vix": float(vix_pct), "gpr": float(gpr_pct)}
    used, warnings = {}, []
    for item in spec["inputs"]:
        k = item["name"].removesuffix("_pct")
        v = min(max(requested[k], item["hard_min"]), item["hard_max"])
        if v != requested[k]:
            warnings.append(f"{k}_pct clamped from {requested[k]} to {v} (outside anything seen 2010–2026).")
        elif not item["slider_min"] <= v <= item["slider_max"]:
            warnings.append(f"{k}_pct={v} is more extreme than 99% of historical 20-day moves.")
        used[k] = v

    s = {k: np.log1p(used[k] / 100) for k in INPUTS}
    terms = {k: model["shrink"] * e["coef"][k] * s[k] for k in INPUTS}
    med = sum(terms.values())

    def band(day):
        frac = day / H
        w = a["sigma30"] * np.sqrt(day) * np.exp(model["gamma"] * s["vix"] * frac)
        m = med * frac
        return a["brent"] * np.exp([m + e["z_lo"] * w, m, m + e["z_hi"] * w])

    path = [{"day": 0, "date": a["date"], "p10": a["brent"], "p50": a["brent"], "p90": a["brent"]}]
    for day in range(1, H + 1):
        lo, mid, hi = band(day)
        point = {"day": day, "date": dates[day - 1],
                 "p10": round(float(lo), 2), "p50": round(float(mid), 2), "p90": round(float(hi), 2)}
        if dates[day - 1] in actual:
            point["actual"] = round(float(actual[dates[day - 1]]), 2)
        path.append(point)

    final = path[-1]
    move = final["p50"] - a["brent"]
    total = sum(terms.values())
    contributions = {k: {"log_change": round(float(terms[k]), 5),
                         "pct": round(float(100 * np.expm1(terms[k])), 3),
                         "usd": round(float(move * terms[k] / total), 2) if total else 0.0} for k in INPUTS}

    ci = e.get("coef_ci95", {})
    for k in INPUTS:
        if k in ci and ci[k][1] <= 0 <= ci[k][2] and used[k] != 0:
            warnings.append(f"In the '{e['label']}' era the {k.upper()} effect is not statistically "
                            "distinguishable from zero.")

    lo_hist, hi_hist = _history()["sigma30"].min(), _history()["sigma30"].max()
    if not lo_hist <= a["sigma30"] <= hi_hist:
        warnings.append(f"sigma30={a['sigma30']:.4f} is outside the 2010–2026 range "
                        f"({lo_hist:.4f}–{hi_hist:.4f}); check its units.")
    if a["date"] > model["anchor"]["date"]:
        warnings.append(f"Starting after the training data ends ({model['anchor']['date']}); "
                        "relationships are from 2010–2026 history.")

    return {
        "as_of": a["date"], "spot": a["brent"], "sigma30": round(a["sigma30"], 6),
        "anchor_source": source,
        "era": era, "era_label": e["label"],
        "horizon_days": H, "inputs_requested": requested, "inputs_used": used,
        "summary": {"p10": final["p10"], "p50": final["p50"], "p90": final["p90"],
                    "median_change_pct": round(float(100 * np.expm1(med)), 3)},
        "path": path, "contributions": contributions, "warnings": warnings,
        "disclaimer": "Conditional, educational model: 'if these things happen, what range is plausible "
                      "based on 2010–2026 history'. Not a forecast; not for trading.",
    }
