"""Backtest the injury flag on 2025-26: would the games-played rule have steered this league's real draft away from lost picks?
Uses the league's actual 2025 draft (data/league_draft_2025.json), ESPN actuals, and the same history rule as build.py."""
import json, statistics as st, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as b

cur = {b.norm(p["player"]["fullName"]): p["player"] for p in json.load(open(b.D("raw", "espn_players_2026.json")))["players"]}
h25, h24 = b.load_history(2025), b.load_history(2024)
MY_TEAM = "Your team name"  # set to your Yahoo team name
draft = json.load(open(b.D("league_draft_2025.json")))  # your league's past draft; not included in the public repo
CATS = b.CATS

def raw(x, lg_fg, lg_ft):
    return dict(fg=(x["fgm"] / x["fga"] - lg_fg) * x["fga"] if x["fga"] else 0, ft=(x["ftm"] / x["fta"] - lg_ft) * x["fta"] if x["fta"] else 0,
                tpm=x["tpm"], pts=x["pts"], reb=x["reb"], ast=x["ast"], stl=x["stl"], blk=x["blk"], tov=-x["tov"])

rows = []
for d in draft:
    k = b.norm(d["name"]); pl = cur.get(k)
    act = b.espn_block(pl, "002026") if pl else None
    rot = [h for h in (h25.get(k), h24.get(k)) if h and h["mpg"] >= 18]
    two = sum(h["gp"] for h in rot) / len(rot) if len(rot) == 2 else None
    flag = "risk" if (two is not None and two < 55) or (len(rot) == 1 and rot[0]["gp"] < 50) else "clean"
    rows.append(dict(d, act=act, flag=flag, two=two, gp=act["gp"] if act else 0))

pool = [r["act"] for r in rows if r["act"] and r["act"]["fga"]]
lg_fg = sum(x["fgm"] for x in pool) / sum(x["fga"] for x in pool); lg_ft = sum(x["ftm"] for x in pool) / sum(x["fta"] for x in pool)
stats = {c: (st.mean([raw(x, lg_fg, lg_ft)[c] for x in pool]), st.pstdev([raw(x, lg_fg, lg_ft)[c] for x in pool])) for c in CATS}
for r in rows:
    if r["act"] and r["act"]["fga"]:
        z = sum((raw(r["act"], lg_fg, lg_ft)[c] - stats[c][0]) / stats[c][1] for c in CATS)
        r["season"] = (z + 3) * r["gp"] / 82  # per-game value above a waiver-level player, scaled by games actually played
    else:
        r["season"] = 0
for i, r in enumerate(sorted(rows, key=lambda r: -r["season"])):
    r["finish"] = i + 1

def line(label, rs):
    if not rs: return
    print(f"{label:<28} n={len(rs):<3} avg GP {st.mean(r['gp'] for r in rs):5.1f} | under 55 GP: {100*sum(r['gp']<55 for r in rs)/len(rs):3.0f}% | "
          f"median finish minus pick: {st.median(r['finish']-r['pick'] for r in rs):+5.0f} | beat their pick: {100*sum(r['finish']<=r['pick'] for r in rs)/len(rs):3.0f}%")

for lo, hi in ((1, 36), (37, 96), (97, 156)):
    seg = [r for r in rows if lo <= r["pick"] <= hi]
    print(f"--- picks {lo}-{hi}")
    line("  flagged RISK by the rule", [r for r in seg if r["flag"] == "risk"])
    line("  clean", [r for r in seg if r["flag"] == "clean"])
print("--- by team: RISK picks in rounds 1-9, and how many of those played under 55")
for t in sorted({r["team"] for r in rows}):
    rs = [r for r in rows if r["team"] == t and r["rd"] <= 9 and r["flag"] == "risk"]
    print(f"  {t:<28} {len(rs)} risk picks, {sum(r['gp']<55 for r in rs)} lost | all-13 avg GP {st.mean(r['gp'] for r in rows if r['team']==t):.0f}")
me = [r for r in rows if r["team"] == MY_TEAM]
print("Me:", [(r["rd"], r["name"], r["flag"], int(r["gp"]), r["finish"]) for r in me])
