# makefun-gta6-twitch-ccu-forecast-01

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/people871/makefun-gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/people871/makefun-gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

A forecaster for Grand Theft Auto VI's launch-day Twitch audience: one hour
into release day (2026-11-19 UTC) it predicts, hour by hour, how many people
will be watching the game live on Twitch in each of the other 23 hours, as
five quantiles (5%, 25%, 50%, 75%, 95%) per hour.

How it works: it anchors on the first hour's viewer count, then learns the
launch-day shape from the case's own comparables — past big launches' hourly
curves. It keeps only the rolling-midnight launches (a simultaneous global
unlock is a different animal: its first hour is near-empty and it rises
100–2000x), and measures how deep the first hour sits below the previous
evening's peak. A deep trough means the big markets have not unlocked yet,
so the day rises much further. Per hour, a locally weighted regression of
the log viewer ratio on that trough depth gives the median; the residual
spread gives the quantiles. Nothing is fitted in advance — everything is
computed from the case file at run time, offline, with the standard library
only, and the output is deterministic.

On the four practice launches (answers reconstructed from SullyGnome's
public hourly series) it scores a pinball loss of 0.216, against the house
persistence baseline's 0.387 — typical miss 41% vs 83%.

## Run it

```sh
python3 main.py
```

It reads every case in `$MAKEFUN_INPUT_DIR` (default `/input`) and writes
one forecast per case to `$MAKEFUN_OUTPUT_DIR` (default `/output`). To run
it on the practice cases from the kit:

```sh
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
