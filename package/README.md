# oil_model: Brent 20-day scenario model

Requires numpy and pandas. Keep `oil_model/` and `artifacts/` side by side.

```python
from oil_model import forecast, feature_spec, history, event_analogs
forecast(dxy_pct=2, vix_pct=40, gpr_pct=50)
```

The model is focused on predicting the trajectory of the Brent oil price in the future for the next 20 trading days. Here, we can adjust the values of the US dollar stength, volatility index, and Geopolitical Risk Index through sliders to see how the oil prices will change each day for the next 20 days. 

| Function | Returns |
|---|---|
| `forecast(...)` | 20-day price fan for a scenario (below) |
| `feature_spec()` | slider names, labels, ranges, defaults and the era list |
| `history(days=250, as_of=None)` | `[{date, brent, dxy, vix, gpr}, …]` up to `as_of` (default: 2026-03-12) |
| `event_analogs()` | 35 past events, each with the 5- and 20-day changes in Brent, DXY, VIX and GPR that followed |

## `forecast()` parameters
All parameters are optional keyword arguments. `forecast()` alone returns the baseline: median = starting price.

**Scenario.** Each input is a % change over the next 20 trading days. Values beyond the *clamp* range are clamped, with a warning.

| Parameter | Type | Default | Slider | Clamp | Meaning |
|---|---|---|---|---|---|
| `dxy_pct` | float | `0.0` | −5 to 5 | −8 to 8 | US dollar index change |
| `vix_pct` | float | `0.0` | −43 to 116 | −57 to 505 | VIX change; moves the median and widens or narrows the interval |
| `gpr_pct` | float | `0.0` | −34 to 67 | −41 to 203 | Geopolitical Risk index change; almost no effect on the median |
| `era` | `"all"` \| `"2010-2019"` \| `"2021-2026"` | `"all"` | — | — | Which period's fitted relationships to apply |

**Starting point.** Pass at most one option. The default start is 2026-03-12. Only the starting price and volatility change; the relationships stay those learned from 2010–2026.

| Parameter | Type | Meaning |
|---|---|---|
| `spot` | float | Today's Brent price in USD, > 0. Requires `sigma30`. |
| `sigma30` | float | Brent's 30-day volatility as a **daily fraction**, e.g. 0.021 (see units below). Requires `spot`. |
| `date` | `"YYYY-MM-DD"` | Date of `spot`/`sigma30`. Defaults to today. Only valid with `spot` and `sigma30`. |
| `as_of` | `"YYYY-MM-DD"` | A past start date, 2010-02-17 or later. Non-trading days roll back to the previous trading day. Path points include `"actual"`, the real price that followed. |
| `prices` | `[{"date", "brent"}, …]` | At least 31 recent daily closes, in any order. The fan starts from the latest close, and σ30 is computed from the last 30 returns. |

**σ30 units.** σ30 is the standard deviation of the last 30 daily simple returns, including today, as a daily fraction.
* Convert other forms first: divide an annualized figure by √252 ≈ 15.9, and a percentage by 100.
* A value above 0.2 is rejected as almost certainly annualized or in percent.
* A value outside the 2010–2026 range of 0.0058–0.0886 is accepted, with a warning.

## Returns
A JSON-serializable dict:

| Field | Content |
|---|---|
| `as_of`, `spot`, `sigma30` | start date, starting price (USD) and daily volatility used |
| `anchor_source` | `"history"`, `"prices"` or `"spot"` |
| `era`, `era_label`, `horizon_days` | era key, display name, and `20` |
| `inputs_requested`, `inputs_used` | `{dxy, vix, gpr}` in %, before and after clamping |
| `summary` | `p10`, `p50`, `p90` in USD at day 20, and `median_change_pct` |
| `path` | 21 points (day 0, then 20 US trading days): `{day, date, p10, p50, p90[, actual]}` |
| `contributions` | per input: `{log_change, pct, usd}`; the `usd` values sum to `p50 − spot` |
| `warnings`, `disclaimer` | text to show the user |

## Errors
`forecast()` raises `ValueError` in these cases:
* an unknown `era`, or `as_of` before 2010-02-17;
* fewer than 31 `prices`;
* `spot` without `sigma30` or the reverse, or `date` without `spot`;
* `spot` ≤ 0, or `sigma30` outside (0, 0.2];
* more than one starting-point option.

This is a conditional, educational model, not a forecast, and it is not for trading.
