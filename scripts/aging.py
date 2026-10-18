"""Aging curve for 9-cat fantasy value, from Basketball Reference per-game data (2005 to 2026 seasons).
For every player who was a healthy rotation starter-level player in season t (24+ mpg, 50+ games), look at season t+1 and
measure the change in per-game 9-cat value and in games played, grouped by his age in season t+1. Writes data/aging.json."""
import csv, json, os, statistics as st
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON_GAMES = {2012: 66, 2020: 72, 2021: 72}
rows = {}
for r in csv.DictReader(open(os.path.join(ROOT, "data", "raw", "bbref_per_game.csv"), encoding="utf-8")):
    if r["lg"] != "NBA" or int(r["season"]) < 2005:
        continue
    try:
        x = dict(season=int(r["season"]), id=r["player_id"], name=r["player"], age=int(r["age"]), g=int(r["g"]), mp=float(r["mp_per_game"]),
                 fgm=float(r["fg_per_game"]), fga=float(r["fga_per_game"]), ftm=float(r["ft_per_game"]), fta=float(r["fta_per_game"]),
                 tpm=float(r["x3p_per_game"] or 0), pts=float(r["pts_per_game"]), reb=float(r["trb_per_game"]), ast=float(r["ast_per_game"]),
                 stl=float(r["stl_per_game"]), blk=float(r["blk_per_game"]), tov=float(r["tov_per_game"]))
    except ValueError:
        continue
    k = (x["id"], x["season"])
    if k not in rows or x["g"] > rows[k]["g"]:  # traded players: keep the season-total row
        rows[k] = x

CATS = ["fg", "ft", "tpm", "pts", "reb", "ast", "stl", "blk", "tov"]
by_season = defaultdict(list)
for x in rows.values():
    by_season[x["season"]].append(x)
for season, ps in by_season.items():
    pool = sorted([p for p in ps if p["mp"] >= 24 and p["g"] >= 40], key=lambda p: -p["pts"])
    lg_fg = sum(p["fgm"] for p in pool) / sum(p["fga"] for p in pool); lg_ft = sum(p["ftm"] for p in pool) / sum(p["fta"] for p in pool)
    raw = lambda p: dict(fg=(p["fgm"] / p["fga"] - lg_fg) * p["fga"] if p["fga"] else 0, ft=(p["ftm"] / p["fta"] - lg_ft) * p["fta"] if p["fta"] else 0,
                         tpm=p["tpm"], pts=p["pts"], reb=p["reb"], ast=p["ast"], stl=p["stl"], blk=p["blk"], tov=-p["tov"])
    stats = {c: (st.mean(raw(p)[c] for p in pool), st.pstdev([raw(p)[c] for p in pool]) or 1) for c in CATS}
    full = SEASON_GAMES.get(season, 82)
    for p in ps:
        rw = raw(p)
        p["z"] = {c: (rw[c] - stats[c][0]) / stats[c][1] for c in CATS}
        p["zsum"] = sum(p["z"].values())
        p["g82"] = min(82, p["g"] * 82 / full)

pairs = defaultdict(list)
for (pid, season), a in rows.items():
    b = rows.get((pid, season + 1))
    if a["mp"] >= 24 and a["g82"] >= 50 and season + 1 <= 2026:
        if b is None:  # out of the league or missed the whole year
            pairs[a["age"] + 1].append(dict(dz=None, g=0, dg=-a["g82"], dmp=None, cats=None))
        else:
            pairs[b["age"]].append(dict(dz=b["zsum"] - a["zsum"], g=b["g82"], dg=b["g82"] - a["g82"], dmp=b["mp"] - a["mp"],
                                        cats={c: b["z"][c] - a["z"][c] for c in CATS}))

out = {}
print(f"{'age':>3} {'n':>4} {'d value/gm':>10} {'games':>6} {'under55':>8} {'d min':>6}   biggest category moves")
for age in range(20, 40):
    ps = pairs.get(age, [])
    if len(ps) < 25:
        continue
    played = [p for p in ps if p["dz"] is not None]
    dz = st.mean(p["dz"] for p in played); g = st.mean(p["g"] for p in ps); u55 = sum(p["g"] < 55 for p in ps) / len(ps)
    cats = {c: st.mean(p["cats"][c] for p in played) for c in CATS}
    out[age] = dict(n=len(ps), dz=round(dz, 3), games=round(g, 1), under55=round(u55, 3), dmp=round(st.mean(p["dmp"] for p in played), 2),
                    cats={c: round(v, 3) for c, v in cats.items()})
    top = sorted(cats.items(), key=lambda kv: kv[1])
    print(f"{age:>3} {len(ps):>4} {dz:>+10.2f} {g:>6.1f} {100*u55:>7.0f}% {out[age]['dmp']:>+6.1f}   " + ", ".join(f"{c} {v:+.2f}" for c, v in top[:2] + top[-1:]))

# simple least-squares fits, weighted by sample size, so the board can use a smooth curve instead of noisy per-age means
def wfit(xs, ys, ws, deg):
    import numpy as np
    return [float(v) for v in np.polyfit(xs, ys, deg, w=[w ** .5 for w in ws])]
ages = sorted(out)
try:
    fit_dz = wfit(ages, [out[a]["dz"] for a in ages], [out[a]["n"] for a in ages], 2)
    fit_u55 = wfit(ages, [out[a]["under55"] for a in ages], [out[a]["n"] for a in ages], 2)
    fit_g = wfit(ages, [out[a]["games"] for a in ages], [out[a]["n"] for a in ages], 2)
except ImportError:
    fit_dz = fit_u55 = fit_g = None
json.dump(dict(by_age=out, fit_dz=fit_dz, fit_u55=fit_u55, fit_games=fit_g, seasons="2005-2026", rule="24+ mpg and 50+ games (82-game pace) in the prior season"),
          open(os.path.join(ROOT, "data", "aging.json"), "w"), indent=1)
if fit_dz:
    f = lambda c, a: c[0] * a * a + c[1] * a + c[2]
    print("smoothed:", "  ".join(f"{a}: {f(fit_dz, a):+.2f} val, {f(fit_g, a):.0f} gp, {100*f(fit_u55, a):.0f}% <55" for a in (22, 25, 28, 30, 32, 34, 36)))
    import math
    a, b, c = fit_dz; disc = b * b - 4 * a * c
    if disc > 0: print("per-game value starts falling at age", round(min((-b + math.sqrt(disc)) / (2 * a), (-b - math.sqrt(disc)) / (2 * a)), 1), "/", round(max((-b + math.sqrt(disc)) / (2 * a), (-b - math.sqrt(disc)) / (2 * a)), 1))
