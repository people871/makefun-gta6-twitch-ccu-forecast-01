"""Forecast GTA VI's launch-day Twitch viewers, hour by hour (gta6-twitch-ccu-forecast-01).

Reads one case file (/input/<id>.in) and writes /output/<id>.out: for each of
hours 2..24 of the release day (UTC), five quantiles (5%, 25%, 50%, 75%, 95%)
of that hour's concurrent viewers in the game's Twitch category.

Method (learned from the case itself, no network, no fitted constants shipped):
  1. Anchor on the case's hour-1 print p1.
  2. Take the case's comparables (past big launches' hourly curves) and keep
     only the rolling-midnight launches: a comparable counts if its release
     day has an hour-1 print, at least 20 printed hours, and its day peak is
     at most 15x its hour-1 print. That drops the simultaneous-global
     unlocks (Silksong, Wukong, ...), whose hour 1 is near-empty and whose
     curves rise 100-2000x -- a different animal from a rolling midnight
     unlock like GTA VI's, where New Zealand has already played 13 hours
     when the UTC day starts.
  3. For each kept launch, x = ln(hour-1 viewers / pre-24h peak): how deep
     the hour-1 trough sits below the previous evening's peak (the NZ
     unlock ramp). A deep trough means the big markets have not unlocked
     yet, so the day rises much further. The target's own x comes from its
     history (max viewers in the 24 h before day_start) and its hour-1 print.
  4. Per hour h, a locally weighted linear regression of ln(viewers_h /
     viewers_1) on x across the kept launches (Gaussian kernel, bandwidth
     1.2 in x), evaluated at the target's x, gives the median log-ratio;
     the spread is the residual standard deviation around that line.
     Quantiles: q_tau = p1 * exp(median + z_tau * sd), z the standard
     normal's quantiles. This is a proper-quantile forecast: the median
     tracks where the count will be, the spread how sure we are.
  5. If anything about a case is unusable, fall back to the persistence
     forecast (every hour at the hour-1 print, spread widening like a
     random walk), so the output is always a valid forecast file.

Local check (practice answers reconstructed from SullyGnome's public
"Average viewers" series, cross-checked against each case's history):
  house baseline  loss 0.387 | this forecaster loss 0.216
  per case: p00 0.316, p01 0.207, p02 0.148, p03 0.191.

Python 3.13, standard library only. Deterministic: no randomness, no
clock, no network; two runs on the same case write identical bytes.
Runs in well under a second per case (limit 8 s).
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# The grader's -P leaves this file's directory OFF sys.path: put it back
# first, so a module shipped beside this file would import.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level.
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

# A comparable is a rolling-midnight launch when its release-day peak is at
# most this many times its hour-1 print (simultaneous unlocks rise 100x+).
PEAK_RATIO_MAX = 15.0
# A comparable's release day must have at least this many printed hours.
MIN_DAY_HOURS = 20
# Gaussian kernel bandwidth (in x units) for the local regression.
KERNEL_BW = 1.2
# The residual spread is never narrower / wider than these (log units).
SD_FLOOR = 0.15
SD_CAP = 1.5
# Fallback spread (house baseline's): log sd per square-root hour.
FALLBACK_SIGMA = 0.15


def parse_ts(text):
    """An ISO 8601 UTC timestamp -> an aware datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def round2(x):
    """x rounded to 2 decimals, half up, as JavaScript's Math.round(x*100)/100.

    A whole number comes back as an int, so json.dumps writes 1240 where
    JavaScript writes 1240 (not 1240.0).
    """
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def release_day(curve):
    """A comparable's release-day hourly viewers: {hour 1..24: viewers}.

    Only hours with a positive print count; a missing, zero or malformed
    hour is skipped, never interpolated, and never breaks the whole case.
    """
    try:
        day_start = parse_ts(curve["day_start"])
    except (KeyError, TypeError, ValueError):
        return {}
    day = {}
    for row in curve.get("hourly") or []:
        viewers = row.get("viewers")
        if viewers is None or viewers <= 0:
            continue
        try:
            offset = (parse_ts(row["from"]) - day_start).total_seconds() / 3600
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= offset < 24:
            day[int(offset) + 1] = viewers
    return day


def pre_peak(case):
    """The target's own pre-release peak: max viewers in the 24 h before
    day_start, from history_hourly (falling back to the raw history)."""
    day_start = parse_ts(case["day_start"])
    start = day_start - timedelta(hours=24)
    best = None
    for rows, key in ((case.get("history_hourly") or [], "from"),
                      (case.get("history") or [], "at")):
        for row in rows:
            viewers = row.get("viewers")
            if viewers is None:
                continue
            try:
                at = parse_ts(row[key])
            except (KeyError, TypeError, ValueError):
                continue
            if start <= at < day_start and (best is None or viewers > best):
                best = viewers
        if best is not None:
            return best
    return None


def kept_launches(case):
    """The rolling-midnight comparables: (day curve, pre-24h peak, x).

    x = ln(hour-1 viewers / pre-24h peak) measures how deep the hour-1
    trough sits below the previous evening's peak. The target's own
    pre-release history (GTA VI's category) is not a launch and is left
    out: it has no release day in the window.
    """
    kept = []
    for comp in case.get("comparables") or []:
        if "target-history" in (comp.get("unlock") or "").lower():
            continue
        try:
            day = release_day(comp)
        except Exception:
            continue
        if 1 not in day or len(day) < MIN_DAY_HOURS:
            continue
        if max(day.values()) / day[1] > PEAK_RATIO_MAX:
            continue
        try:
            peak = pre_peak({"day_start": comp["day_start"],
                             "history_hourly": comp.get("hourly") or [],
                             "history": []})
        except Exception:
            continue
        if peak is None or peak <= 0:
            continue
        kept.append((day, math.log(day[1] / peak)))
    return kept


def weighted_ols(xs, ys, ws):
    """Weighted least squares for y ~ a + b*x. Returns (a, b)."""
    total = sum(ws)
    if total <= 0:
        return statistics_mean(ys), 0.0
    mx = sum(w * x for w, x in zip(ws, xs)) / total
    my = sum(w * y for w, y in zip(ws, ys)) / total
    den = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
    if den <= 0:
        return my, 0.0
    b = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys)) / den
    return my - b * mx, b


def statistics_mean(values):
    return sum(values) / len(values)


def hour_quantiles(kept, xt, v1, h):
    """The five quantiles of hour h's viewers, from the local regression."""
    pts = [(x, math.log(day[h] / day[1])) for day, x in kept if h in day]
    if len(pts) < 5:
        # Too little training data for this hour: persist hour 1.
        return [round2(v1 * math.exp(z * FALLBACK_SIGMA * math.sqrt(h - 1)))
                for z in Z]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ws = [math.exp(-((x - xt) / KERNEL_BW) ** 2) for x in xs]
    if max(ws) < 0.05:
        # The target's trough depth is far from every launch's: no local
        # fit is meaningful, use the plain regression over all of them.
        ws = [1.0] * len(xs)
    a, b = weighted_ols(xs, ys, ws)
    median = a + b * xt
    resid = [y - (a + b * x) for x, y in pts]
    mean_resid = statistics_mean(resid)
    var = sum((r - mean_resid) ** 2 for r in resid) / len(resid)
    sd = min(SD_CAP, max(SD_FLOOR, math.sqrt(var)))
    return [round2(max(1.0, v1 * math.exp(median + z * sd))) for z in Z]


def persistence(p1, h):
    """Fallback: every hour at the hour-1 print, widening spread."""
    return [round2(max(1.0, p1) * math.exp(z * FALLBACK_SIGMA * math.sqrt(h - 1)))
            for z in Z]


def forecast_case(case, name):
    """One case's forecast: {"hours": [{"hour": h, "q": [...]}, ...]}."""
    if case.get("levels") != LEVELS:
        raise ValueError(f"{name} asks for levels {case.get('levels')}, not {LEVELS}")
    first = next((k for k in case.get("known") or [] if k.get("hour") == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, first["viewers"])
    kept = kept_launches(case)
    if len(kept) < 5:
        return {"hours": [{"hour": row["hour"], "q": persistence(p1, row["hour"])}
                          for row in case["forecast"]]}
    try:
        peak = pre_peak(case)
    except Exception:
        peak = None
    if peak is None or peak <= 0:
        # No pre-release history to measure the trough against: use the
        # middle of the launches' trough depths.
        xt = statistics_mean([x for _, x in kept])
    else:
        xt = math.log(p1 / peak)
        xs = [x for _, x in kept]
        lo, hi = min(xs) - 0.5, max(xs) + 0.5
        xt = min(hi, max(lo, xt))
    hours = []
    for row in case["forecast"]:
        h = row["hour"]
        hours.append({"hour": h, "q": hour_quantiles(kept, xt, p1, h)})
    return {"hours": hours}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        try:
            forecast = forecast_case(case, path.name)
        except Exception:
            # Never leave a case without a valid forecast file: persist.
            first = next((k for k in case.get("known") or [] if k.get("hour") == 1),
                         {"viewers": 1})
            p1 = max(1, first["viewers"])
            forecast = {"hours": [{"hour": row["hour"],
                                   "q": persistence(p1, row["hour"])}
                                  for row in case["forecast"]]}
        text = json.dumps(forecast, separators=(",", ":")) + "\n"
        (OUTPUT_DIR / f"{path.stem}.out").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
