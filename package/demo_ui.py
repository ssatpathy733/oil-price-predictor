"""Interactive demo of oil_model.forecast(): drag the sliders and watch the 20-day cone move.

Run from the package folder (next to oil_model/ and artifacts/):
    pip install numpy pandas matplotlib seaborn
    python demo_ui.py
"""
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.widgets import Button, RadioButtons, Slider

from oil_model import feature_spec, forecast, history

HISTORY_DAYS = 60
COLORS = {"dxy": "#4c72b0", "vix": "#c44e52", "gpr": "#8172b2"}

spec = feature_spec()
inputs = spec["inputs"]
eras = spec["eras"]
past = pd.DataFrame(history(days=HISTORY_DAYS))
past["date"] = pd.to_datetime(past["date"])


def run(era, values):
    return forecast(era=era, **values)


def fixed_ylim():
    """Price range that fits the widest cones the sliders can produce, so the axis doesn't jump."""
    lo, hi = past["brent"].min(), past["brent"].max()
    dxy, vix = inputs[0], inputs[1]
    for era in (e["key"] for e in eras):
        for d in (dxy["slider_min"], dxy["slider_max"]):
            for v in (vix["slider_min"], vix["slider_max"]):
                s = run(era, {"dxy_pct": d, "vix_pct": v, "gpr_pct": 0.0})["summary"]
                lo, hi = min(lo, s["p10"]), max(hi, s["p90"])
    pad = 0.05 * (hi - lo)
    return lo - pad, hi + pad


sns.set_theme(style="whitegrid", context="notebook")
fig = plt.figure(figsize=(13, 8))
fig.canvas.manager.set_window_title("Brent 20-day scenario model")

ax = fig.add_axes([0.06, 0.40, 0.62, 0.52])
ax_contrib = fig.add_axes([0.76, 0.40, 0.21, 0.52])

# History and cone. The cone polygon is redrawn on every update; the lines are updated in place.
ax.plot(past["date"], past["brent"], color="0.25", lw=1.6, label=f"Brent, last {HISTORY_DAYS} days")
(median_line,) = ax.plot([], [], color="#dd8452", lw=2.2, label="Median (p50)")
(p10_line,) = ax.plot([], [], color="#dd8452", lw=0.8, ls="--")
(p90_line,) = ax.plot([], [], color="#dd8452", lw=0.8, ls="--")
cone = None
ax.set_ylim(*fixed_ylim())
ax.set_ylabel("Brent (USD/bbl)")
warning_text = fig.text(0.06, 0.335, "", fontsize=8.5, color="#b5651d", va="top", wrap=True)
fig.text(0.5, 0.012, forecast()["disclaimer"], fontsize=8, color="0.45", ha="center")

# Sliders, one per model input, using the 1st–99th percentile range from feature_spec.
sliders = {}
for row, item in enumerate(inputs):
    k = item["name"].removesuffix("_pct")
    s_ax = fig.add_axes([0.20, 0.25 - row * 0.06, 0.42, 0.03])
    sliders[k] = Slider(s_ax, f"{item['label']}\n% change", item["slider_min"], item["slider_max"],
                        valinit=item["default"], valstep=item["step"], color=COLORS[k])
    sliders[k].label.set_fontsize(9)

era_ax = fig.add_axes([0.76, 0.10, 0.21, 0.17])
era_ax.set_title("Era of fitted relationships", fontsize=9)
era_radio = RadioButtons(era_ax, [e["label"] for e in eras], active=0)
era_by_label = {e["label"]: e["key"] for e in eras}

reset_ax = fig.add_axes([0.62, 0.06, 0.06, 0.04])
reset_btn = Button(reset_ax, "Reset")


def update(_=None):
    global cone
    values = {f"{k}_pct": s.val for k, s in sliders.items()}
    r = run(era_by_label[era_radio.value_selected], values)
    path = pd.DataFrame(r["path"])
    dates = pd.to_datetime(path["date"])

    if cone is not None:
        cone.remove()
    cone = ax.fill_between(dates, path["p10"], path["p90"], color="#dd8452", alpha=0.25, lw=0,
                           label="p10–p90 range")
    median_line.set_data(dates, path["p50"])
    p10_line.set_data(dates, path["p10"])
    p90_line.set_data(dates, path["p90"])
    ax.set_xlim(past["date"].iloc[0], dates.iloc[-1])
    ax.legend(loc="upper left", fontsize=9)  # rebuilt so it picks up the new cone

    s = r["summary"]
    # "\$" stops matplotlib reading pairs of dollar signs as math markup.
    ax.set_title(f"Start {r['as_of']}  ·  spot \\${r['spot']:.2f}  →  day 20: "
                 f"p10 \\${s['p10']:.2f}  ·  p50 \\${s['p50']:.2f} ({s['median_change_pct']:+.1f}%)  ·  "
                 f"p90 \\${s['p90']:.2f}", fontsize=10.5)

    # Each input's share of the median move; the bars sum to p50 − spot.
    ax_contrib.clear()
    keys = list(r["contributions"])
    usd = [r["contributions"][k]["usd"] for k in keys]
    ax_contrib.barh([k.upper() for k in keys], usd, color=[COLORS[k] for k in keys])
    ax_contrib.axvline(0, color="0.3", lw=0.8)
    lim = max(1.0, max(abs(u) for u in usd) * 1.3)
    ax_contrib.set_xlim(-lim, lim)
    for i, u in enumerate(usd):
        ax_contrib.text(u, i, f" {u:+.2f} ", va="center", ha="left" if u >= 0 else "right", fontsize=9)
    ax_contrib.invert_yaxis()
    ax_contrib.set_title(f"Contribution to median move (USD)\nTotal {s['p50'] - r['spot']:+.2f}",
                         fontsize=10)

    warning_text.set_text("\n".join("⚠ " + w for w in r["warnings"]))
    fig.canvas.draw_idle()


def reset(_):
    for s in sliders.values():
        s.reset()  # each reset fires update()


for s in sliders.values():
    s.on_changed(update)
era_radio.on_clicked(update)
reset_btn.on_clicked(reset)

update()
plt.show()
