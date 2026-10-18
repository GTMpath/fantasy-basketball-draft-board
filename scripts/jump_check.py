"""Older players coming off a jump season: how much more of the jump does the projection keep than history says he will?

Reads data/last_season_jump.json (ids and 2025-26 jump), data/raw/bbref_per_game.csv and the blended projection in
data/players.json, then writes jump_pen, jump_kind and z3 (2023-24, 2024-25, 2025-26 per-game value) back into the
jump file for every player 29+ with a jump of 1.5 or more. Run after build.py, then run build.py again.

Why it is per player and not a flat age penalty (adversarial review, 2026-10-15):
- Against a regressed baseline, older jumpers as a group do no worse than their peers, so a flat penalty double counts
  whenever the projection already pulls the player back (Bridges and Brown keep about a quarter of their jump).
- ESPN's own 2024-25 and 2025-26 projections still missed age 29+ jumpers by about 1.1 z more than other players
  (n=22), so where a projection keeps most of the jump, the excess is real.
Expected next-season value by case (bbref history 2005-26):
- jump came off a season under 50 games: pre-jump level + 0.6 x jump (most of it was health, and health comes back)
- 32+: pre-jump level + 0.2
- 29-31 bounce-back (2025-26 no better than 2023-24 + 0.5): three-season mean - 0.4
- 29-31 new high: pre-jump level + 0.25 x jump
Penalty = 0.7 x (projection - expected), clamped to [0, 1.2] before scaling.
"""
import csv, json, os, statistics as st, sys

sys.path.insert(0, os.path.dirname(__file__))
import build as B

R = os.path.join(os.path.dirname(__file__), "..", "data")
CATS = B.CATS


def raw(x, lg_fg, lg_ft):
    return dict(fg=(x["fgm"] / x["fga"] - lg_fg) * x["fga"] if x["fga"] else 0,
                ft=(x["ftm"] / x["fta"] - lg_ft) * x["fta"] if x["fta"] else 0,
                tpm=x["tpm"], pts=x["pts"], reb=x["reb"], ast=x["ast"], stl=x["stl"], blk=x["blk"], tov=-x["tov"])


rows = {}
for r in csv.DictReader(open(os.path.join(R, "raw", "bbref_per_game.csv"), encoding="utf-8")):
    if r["lg"] != "NBA" or int(r["season"]) < 2024:
        continue
    try:
        x = dict(season=int(r["season"]), name=B.norm(r["player"]), g=int(r["g"]), mp=float(r["mp_per_game"]),
                 fgm=float(r["fg_per_game"]), fga=float(r["fga_per_game"]), ftm=float(r["ft_per_game"]),
                 fta=float(r["fta_per_game"]), tpm=float(r["x3p_per_game"] or 0), pts=float(r["pts_per_game"]),
                 reb=float(r["trb_per_game"]), ast=float(r["ast_per_game"]), stl=float(r["stl_per_game"]),
                 blk=float(r["blk_per_game"]), tov=float(r["tov_per_game"]))
    except ValueError:
        continue
    k = (x["name"], x["season"])
    if k not in rows or x["g"] > rows[k]["g"]:
        rows[k] = x

# every season scored on the 2025-26 scale so the three seasons and the projection are comparable
pool = [p for (n, s), p in rows.items() if s == 2026 and p["mp"] >= 24 and p["g"] >= 40]
LF = sum(p["fgm"] for p in pool) / sum(p["fga"] for p in pool)
LT = sum(p["ftm"] for p in pool) / sum(p["fta"] for p in pool)
NORM = {c: (st.mean(raw(p, LF, LT)[c] for p in pool), st.pstdev([raw(p, LF, LT)[c] for p in pool])) for c in CATS}


def z(x):
    rw = raw(x, LF, LT)
    return sum((rw[c] - NORM[c][0]) / NORM[c][1] for c in CATS)


players = {p["id"]: p for p in json.load(open(os.path.join(R, "players.json")))}
path = os.path.join(R, "last_season_jump.json")
jumps = json.load(open(path))
for j in jumps:
    for k in ("jump_pen", "jump_kind", "z3"):
        j.pop(k, None)
    p = players.get(j["id"])
    if not p or not p.get("age") or p["age"] < 29 or (j["jump"] or 0) < 1.5:
        continue
    a, b, c = rows.get((j["id"], 2025)), rows.get((j["id"], 2026)), rows.get((j["id"], 2024))
    if not a or not b:
        continue
    za, zb, zp = z(a), z(b), z(p)
    z0 = z(c) if c else None
    jump = zb - za
    if a["g"] < 50:
        kind, exp = "injury rebound", za + 0.6 * jump
    elif p["age"] >= 32:
        kind, exp = "career yr", za + 0.2
    elif z0 is not None and zb <= z0 + 0.5:
        kind, exp = "bounce-back", (z0 + za + zb) / 3 - 0.4
    else:
        kind, exp = "career yr", za + 0.25 * jump
    j.update(jump_kind=kind, jump_pen=round(0.7 * max(0, min(1.2, zp - exp)), 2),
             z3=[round(v, 1) if v is not None else None for v in (z0, za, zb)], z_proj=round(zp, 1), z_exp=round(exp, 1))
    print(f"{p['name']:20} {p['age']:>3} {kind:15} 23-24 {z0 if z0 is None else round(z0,1)!s:>5} 24-25 {za:5.1f} ({a['g']}g) "
          f"25-26 {zb:5.1f}  proj {zp:5.1f}  expected {exp:5.1f}  pen {j['jump_pen']}")
json.dump(jumps, open(path, "w"), indent=0)
