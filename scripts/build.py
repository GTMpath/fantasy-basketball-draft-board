"""Merge raw sources into web/data.js for the draft board.

Sources (all under data/):
  raw/espn_players.json        ESPN 2026-27 projections, injury status, outlook text, last season actuals
  raw/espn_players_2026.json   actuals for 2024-25 (games played history)
  raw/espn_players_2025.json   actuals for 2023-24
  raw/hashtag_adp.html         Yahoo / ESPN / Fantrax ADP and Yahoo position eligibility
  hashtag_projections.json     Hashtag top-30 projections (free tier), blended with ESPN where present
  research_injuries.json       optional, hand-verified injury overlay
  research_expert.json         optional, sleeper / bust / role-change tags
  overrides.json               optional, manual edits: {"Player Name": {"flag": "red", "note": "..."}}
"""
import html
import json
import os
import re
import statistics
import unicodedata
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda *p: os.path.join(ROOT, "data", *p)

TEAMS = 12
ROUNDS = 13
POOL = TEAMS * ROUNDS  # players that set the z-score baseline

ESPN_TEAM = {1: "ATL", 2: "BOS", 3: "NOP", 4: "CHI", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GSW", 10: "HOU",
             11: "IND", 12: "LAC", 13: "LAL", 14: "MIA", 15: "MIL", 16: "MIN", 17: "BKN", 18: "NYK", 19: "ORL",
             20: "PHI", 21: "PHX", 22: "POR", 23: "SAC", 24: "SAS", 25: "OKC", 26: "UTA", 27: "WAS", 28: "TOR",
             29: "MEM", 30: "CHA", 0: "FA"}
ESPN_SLOT = {0: "PG", 1: "SG", 2: "SF", 3: "PF", 4: "C"}
S = {"pts": "0", "blk": "1", "stl": "2", "ast": "3", "reb": "6", "tov": "11", "fgm": "13", "fga": "14",
     "ftm": "15", "fta": "16", "tpm": "17", "mpg": "40", "gp": "42"}
CATS = ["fg", "ft", "tpm", "pts", "reb", "ast", "stl", "blk", "tov"]


ALIAS = {"alexandre sarr": "alex sarr", "nicolas claxton": "nic claxton"}


def norm(name):
    n = _norm(name)
    return ALIAS.get(n, n)


def _norm(name):
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.'’]", "", n)
    n = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", n)
    return " ".join(re.sub(r"[^a-z ]", " ", n).split())


def espn_block(player, stat_id):
    for s in player.get("stats", []):
        if s.get("id") == stat_id and s.get("averageStats"):
            a = s["averageStats"]
            return {k: a.get(v) or 0 for k, v in S.items()}
    return None


def load_espn():
    out = {}
    for p in json.load(open(D("raw", "espn_players.json")))["players"]:
        pl = p["player"]
        proj = espn_block(pl, "102027")
        last = espn_block(pl, "002026")
        fallback = False
        if not proj or not proj["pts"] or not proj["fga"]:
            if not last or not last["fga"] or last["gp"] < 20:
                continue
            proj, fallback = dict(last), True  # no ESPN projection: carry last season's line forward
        ranks = pl.get("draftRanksByRankType", {})
        out[norm(pl["fullName"])] = dict(
            name=pl["fullName"], team=ESPN_TEAM.get(pl.get("proTeamId"), "?"),
            espn_pos=[ESPN_SLOT[s] for s in pl.get("eligibleSlots", []) if s in ESPN_SLOT],
            espn_status=pl.get("injuryStatus") or "ACTIVE", outlook=pl.get("seasonOutlook") or "",
            espn_rank=(ranks.get("ROTO") or ranks.get("STANDARD") or {}).get("rank"),
            espn_adp=(pl.get("ownership") or {}).get("averageDraftPosition"),
            proj=proj, last=last, fallback=fallback)
    return out


def load_history(year):
    out = {}
    path = D("raw", f"espn_players_{year}.json")
    if not os.path.exists(path):
        return out
    for p in json.load(open(path))["players"]:
        b = espn_block(p["player"], f"00{year}")
        if b:
            out[norm(p["player"]["fullName"])] = b
    return out


def load_adp():
    s = open(D("raw", "hashtag_adp.html"), encoding="utf-8", errors="ignore").read()
    t = re.search(r'<table id="rawDataTable".*?</table>', s, re.S).group(0)
    out = {}
    for r in re.findall(r"<tr.*?</tr>", t, re.S):
        tds = re.findall(r"<td.*?</td>", r, re.S)
        if len(tds) < 15:
            continue
        c = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", x)).split()) for x in tds]
        a = re.search(r"<a[^>]*>(.*?)</a>", tds[0], re.S)
        name = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", a.group(1))).split()) if a else c[0]
        num = lambda x: float(x) if re.match(r"^[\d.]+$", x) else None
        out[norm(name)] = dict(name=name, team=c[1], yahoo_pos=c[3], yahoo_adp=num(c[4]), espn_adp=num(c[8]),
                               fantrax_adp=num(c[12]), blend_adp=num(c[14]))
    return out


def load_yahoo():
    """Yahoo's own season projections (Rotowire-powered) and pre-season rank for this league, read from the logged-in site."""
    out = {}
    path = D("yahoo_projections.txt")
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        f = line.rstrip("\n").split("|")
        if line.startswith("#") or len(f) < 13:
            continue
        num = lambda x: float(x.replace(",", ""))
        gp = num(f[2])
        if gp <= 0:
            continue
        fgm, fga = (num(x) for x in f[4].split("/")); ftm, fta = (num(x) for x in f[5].split("/"))
        tot = dict(fgm=fgm, fga=fga, ftm=ftm, fta=fta, tpm=num(f[6]), pts=num(f[7]), reb=num(f[8]), ast=num(f[9]), stl=num(f[10]), blk=num(f[11]), tov=num(f[12]))
        out[norm(f[0])] = dict(name=f[0], status=f[1], rank=int(f[3]), gp=gp, **{k: v / gp for k, v in tot.items()})
    return out


PLAYOFF_WEEKS = {19: ("2027-03-08", "2027-03-14"), 20: ("2027-03-15", "2027-03-21"), 21: ("2027-03-22", "2027-03-28")}
SCHED_ABBR = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}


def load_schedule():
    """Games per team in the league's playoff weeks (19 to 21, ending Sun Mar 28) and how many are the second night of a back-to-back."""
    path = D("nba_schedule_2026_27.json")
    if not os.path.exists(path):
        return {}
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    out = {}
    for abbr, dates in json.load(open(path)).items():
        days = sorted({datetime.fromisoformat(d.replace("Z", "+00:00")).astimezone(et).date() for d in dates})
        dayset = set(days)
        wk = {}
        for w, (a, b) in PLAYOFF_WEEKS.items():
            a, b = datetime.fromisoformat(a).date(), datetime.fromisoformat(b).date()
            g = [d for d in days if a <= d <= b]
            wk[w] = dict(g=len(g), b2b=sum((d - timedelta(days=1)) in dayset for d in g))
        out[SCHED_ABBR.get(abbr, abbr)] = dict(weeks=[wk[w]["g"] for w in sorted(wk)], games=sum(x["g"] for x in wk.values()),
                                                 b2b=sum(x["b2b"] for x in wk.values()), season_b2b=sum((d - timedelta(days=1)) in dayset for d in days))
    return out


def opt(path):
    return json.load(open(path)) if os.path.exists(path) else None


def main():
    espn = load_espn()
    h25, h24 = load_history(2025), load_history(2024)
    adp = load_adp()
    yahoo = load_yahoo()
    sched = load_schedule()
    ages = opt(D("ages.json")) or {}
    jumpd = {x["id"]: x for x in (opt(D("last_season_jump.json")) or [])}  # written by aging analysis + scripts/jump_check.py
    jumps = {k: x["jump"] for k, x in jumpd.items()}  # 2025-26 per-game value minus 2024-25
    aging = opt(D("aging.json")) or {}
    curve = lambda coef, a: coef[0] * a * a + coef[1] * a + coef[2]

    def age_adj(age):
        """Half of the historical year-over-year change in per-game value at this age, relative to a 27-year-old.
        Half, because the ESPN and Yahoo projections already price in some aging."""
        if not age or not aging.get("fit_dz"):
            return 0
        a = max(20, min(37, age))
        return round(max(-.5, min(.6, .5 * (curve(aging["fit_dz"], a) - curve(aging["fit_dz"], 27)))), 2)
    for key, y in yahoo.items():  # players Yahoo projects that ESPN does not (mostly rookies)
        if key not in espn and y["fga"] > 0:
            espn[key] = dict(name=y["name"], team=adp.get(key, {}).get("team") or "", espn_pos=[], espn_status="ACTIVE", outlook="", espn_rank=None,
                             espn_adp=None, proj={**{k: y[k] for k in ("pts", "reb", "ast", "stl", "blk", "tov", "tpm", "fgm", "fga", "ftm", "fta", "gp")}, "mpg": 0},
                             last=None, fallback=False, yahoo_only=True)
    ht = {norm(r["name"]): r for r in (opt(D("hashtag_projections.json")) or [])}
    inj = {norm(r["name"]): r for r in (opt(D("research_injuries.json")) or [])}
    # every research pass (articles, video transcripts, mock drafts) shares one schema and is merged here
    research = [r for r in (opt(D(f)) for f in ("research_expert.json", "research_video.json", "research_mocks.json")) if r]
    overrides = {norm(k): v for k, v in (opt(D("overrides.json")) or {}).items()}
    gather = lambda k: [x for r in research for x in r.get(k, [])]
    sources, seen = [], set()
    for s in gather("sources"):
        if s.get("url") not in seen:
            seen.add(s.get("url")); sources.append(s)

    tags = {}
    for kind in ("sleepers", "busts", "breakouts", "role_changes", "rookies"):
        for r in gather(kind):
            tags.setdefault(norm(r["name"]), []).append(
                dict(kind=kind[:-1] if kind != "role_changes" else "role", text=r.get("why") or r.get("change") or r.get("outlook") or "",
                     sources=r.get("sources", [])))
    mock_picks = {}
    mocks = gather("mock_drafts")
    for m in mocks:
        fmt = (m.get("format") or "").lower()
        if "points" in fmt or "16-team" in fmt or "10-team" in fmt:
            continue  # only 12 and 14-team category mocks are comparable to this league's pick numbers
        for pk in m.get("picks", []):
            if pk.get("name") and pk.get("pick"):
                mock_picks.setdefault(norm(pk["name"]), []).append(pk["pick"])
    pairings = [dict(p, anchor_id=norm(p["anchor"]), partner_ids=[norm(x) for x in p.get("partners", [])]) for p in gather("pairings") if p.get("anchor")]

    # Projected minutes 3+ above a healthy (50+ game) 2025-26: in 2024-25 and 2025-26 those players fell 0.57 z/game further
    # short of ESPN's projection than everyone else (n=30, se 0.37). Fit applies about half of that. Starters confirmed by
    # their coach in the Oct 18 sweep are exempt, since the bump is news rather than an assumption.
    CONFIRMED = {norm(n) for n in ("Dylan Harper", "Isaiah Jackson")}
    def role_bump(name, mpg, hist):
        last = next((h for h in hist if h["season"] == "2025-26"), None)
        if not last or last["gp"] < 50 or not mpg or norm(name) in CONFIRMED: return None
        d = round(mpg - last["mpg"], 1)
        return d if d >= 3 else None

    players = []
    for key, e in espn.items():
        a = adp.get(key, {})
        yadp = a.get("yahoo_adp")
        y = yahoo.get(key)
        if yadp is None and (e["espn_rank"] or 999) > 260 and not (y and y["rank"] <= 220):
            continue
        # average every projection set we have for this player: ESPN, Yahoo (Rotowire), Hashtag (top 30 only)
        sets, src = [], []
        if not e.get("yahoo_only"):
            sets.append(e["proj"]); src.append("last season actuals" if e["fallback"] else "ESPN")
        if y:
            sets.append(y); src.append("Yahoo")
        if key in ht:
            sets.append(ht[key]); src.append("Hashtag")
        p = {}
        for k in ("pts", "reb", "ast", "stl", "blk", "tov", "tpm", "fgm", "fga", "ftm", "fta", "mpg", "gp"):
            vals = [s[k] for s in sets if s.get(k)]
            p[k] = sum(vals) / len(vals) if vals else 0
        if not p["fga"]:
            continue

        # games-played history, counting only seasons where he was a rotation player
        hist = []
        for label, blk in (("2025-26", e["last"]), ("2024-25", h25.get(key)), ("2023-24", h24.get(key))):
            if blk and blk.get("gp"):
                hist.append(dict(season=label, gp=int(blk["gp"]), mpg=round(blk.get("mpg") or 0, 1)))
        rot = [h for h in hist if h["mpg"] >= 18]
        w = [0.5, 0.3, 0.2][:len(rot)]
        hist_gp = sum(h["gp"] * x for h, x in zip(rot, w)) / sum(w) if rot else None
        proj_gp = p.get("gp") or 70
        gp = proj_gp if hist_gp is None else 0.55 * proj_gp + 0.45 * hist_gp

        r = inj.get(key)
        flag, reasons = "", []
        st = e["espn_status"]
        if st == "OUT":
            flag = "red"; reasons.append("ESPN lists him OUT")
        elif st in ("DAY_TO_DAY", "QUESTIONABLE", "DOUBTFUL"):
            reasons.append("ESPN lists him day-to-day")
        if hist_gp is not None and len(rot) >= 2:
            two = sum(h["gp"] for h in rot[:2]) / 2
            if two < 55:
                flag = "red" if flag == "red" else "orange"
                reasons.append(f"averaged {two:.0f} games over his last two seasons")
            elif two < 62 and not flag:
                flag = "yellow"; reasons.append(f"averaged {two:.0f} games over his last two seasons")
        elif rot and rot[0]["gp"] < 50 and not flag:
            flag = "yellow"; reasons.append(f"played {rot[0]['gp']} games last season")
        if gp < 58 and flag in ("", "yellow"):
            flag = "orange"; reasons.append(f"projects to about {gp:.0f} games")
        if r:
            missed = r.get("est_games_missed") or 0
            gp = min(gp, 82 - missed)
            stt = r.get("status")
            if stt == "out_long_term" or (stt == "out_weeks" and missed >= 8):
                flag = "red"
            elif missed >= 12 and flag != "red":
                flag = "orange"
            elif stt in ("out_weeks", "chronic_risk", "managed_minutes") and flag != "red":
                flag = "orange"
            elif stt == "questionable_opener" and not flag:
                flag = "yellow"
            reasons.insert(0, f"{r.get('injury', '')}: {r.get('note', '')} Expected back: {r.get('expected_return', 'unknown')}.".strip())
        age = (ages.get(key) or {}).get("age")
        if age and age >= 33 and not flag:
            flag = "yellow"; reasons.append(f"age {age}: starters this age average about {curve(aging['fit_games'], min(age, 37)):.0f} games the next season" if aging.get("fit_games") else f"age {age}")
        o = overrides.get(key, {})
        if "flag" in o:
            flag = o["flag"]
        if o.get("note"):
            reasons.insert(0, o["note"])

        pos = re.findall(r"PG|SG|SF|PF|C", a.get("yahoo_pos") or "/".join(e["espn_pos"]))
        players.append(dict(
            id=key, name=e["name"], team=e["team"], pos=pos,
            yahoo_adp=yadp, blend_adp=a.get("blend_adp"), espn_adp=round(e["espn_adp"], 1) if e["espn_adp"] else None,
            espn_rank=e["espn_rank"], yahoo_rank=(y or {}).get("rank"), yahoo_status=(y or {}).get("status", ""), mpg=round(p.get("mpg") or 0, 1), gp=round(gp), espn_gp=round(proj_gp),
            fgm=p["fgm"], fga=p["fga"], ftm=p["ftm"], fta=p["fta"],
            tpm=p["tpm"], pts=p["pts"], reb=p["reb"], ast=p["ast"], stl=p["stl"], blk=p["blk"], tov=p["tov"],
            hist=hist, flag=flag, reasons=[x for x in reasons if x], espn_status=st,
            inj_source=(r or {}).get("source_url"), inj_conf=(r or {}).get("confidence"),
            outlook=e["outlook"], tags=tags.get(key, []), proj_src=src,
            age=age,
            # rookies get no aging bonus: ESPN's rookie projections for 2024-25 and 2025-26 missed by the same amount as veterans' (n=26)
            age_adj=age_adj(age) if hist else 0, jump=jumps.get(key),
            # age 29+ off a 1.5+ jump; penalty is only the part of the jump the projection keeps beyond what history supports
            peak=bool(age and age >= 29 and (jumps.get(key) or 0) >= 1.5),
            jump_pen=(jumpd.get(key) or {}).get("jump_pen"), jump_kind=(jumpd.get(key) or {}).get("jump_kind"),
            z3=(jumpd.get(key) or {}).get("z3"), z_proj=(jumpd.get(key) or {}).get("z_proj"), z_exp=(jumpd.get(key) or {}).get("z_exp"), last_gp=next((h["gp"] for h in hist if h["season"] == "2025-26"), None),
            min_bump=role_bump(e.get("name") or key, p.get("mpg"), hist),
            po=sched.get(e["team"], {}).get("games"), po_weeks=sched.get(e["team"], {}).get("weeks"), po_b2b=sched.get(e["team"], {}).get("b2b"),
            season_b2b=sched.get(e["team"], {}).get("season_b2b"),
            mock=(round(statistics.mean(mock_picks[key]), 1) if key in mock_picks else None), mock_n=len(mock_picks.get(key, []))))

    # z-scores: two passes so the baseline is the pool of players who actually get drafted
    def zscore(pool):
        lg_fg = sum(x["fgm"] for x in pool) / sum(x["fga"] for x in pool)
        lg_ft = sum(x["ftm"] for x in pool) / sum(x["fta"] for x in pool)
        raw = lambda x: dict(fg=(x["fgm"] / x["fga"] - lg_fg) * x["fga"] if x["fga"] else 0,
                             ft=(x["ftm"] / x["fta"] - lg_ft) * x["fta"] if x["fta"] else 0,
                             tpm=x["tpm"], pts=x["pts"], reb=x["reb"], ast=x["ast"], stl=x["stl"], blk=x["blk"],
                             tov=-x["tov"])
        stats = {}
        for c in CATS:
            vals = [raw(x)[c] for x in pool]
            stats[c] = (statistics.mean(vals), statistics.pstdev(vals) or 1)
        for x in players:
            rw = raw(x)
            x["z"] = {c: round((rw[c] - stats[c][0]) / stats[c][1], 2) for c in CATS}
            x["zsum"] = round(sum(x["z"].values()), 2)
        return lg_fg, lg_ft

    pool = sorted(players, key=lambda x: x["yahoo_adp"] or 999)[:POOL]
    zscore(pool)
    pool = sorted(players, key=lambda x: -x["zsum"])[:POOL]
    lg_fg, lg_ft = zscore(pool)

    players.sort(key=lambda x: -x["zsum"])
    for i, x in enumerate(players):
        x["rank"] = i + 1
        for k in ("fgm", "fga", "ftm", "fta", "tpm", "pts", "reb", "ast", "stl", "blk", "tov"):
            x[k] = round(x[k], 2)

    meta = dict(built=datetime.now().strftime("%Y-%m-%d %H:%M"), teams=TEAMS, rounds=ROUNDS, lg_fg=round(lg_fg, 4),
                lg_ft=round(lg_ft, 4), n=len(players), sched=sched, aging=aging.get("by_age", {}), injuries=len(inj),
                sources=sources, strategy=gather("strategy_notes"), pairings=pairings, punt_builds=gather("punt_builds"),
                mocks=[dict(title=m.get("title"), url=m.get("url"), site=m.get("site"), format=m.get("format"), n=len(m.get("picks", []))) for m in mocks])
    print("players", len(players), "| with yahoo adp", sum(1 for x in players if x["yahoo_adp"]),
          "| flags", {f: sum(1 for x in players if x["flag"] == f) for f in ("red", "orange", "yellow")})
    unmatched = [v["name"] for k, v in adp.items() if k not in espn and (v["yahoo_adp"] or 999) < 160]
    print("ADP names with no ESPN match:", unmatched)
    known = {x["id"] for x in players}
    offboard = [dict(name=r["name"], team=r.get("team"), kind=k[:-1], text=r.get("why") or r.get("outlook") or "", sources=r.get("sources", []),
                     yahoo_adp=adp.get(norm(r["name"]), {}).get("yahoo_adp"))
                for k in ("sleepers", "breakouts", "rookies") for r in gather(k) if norm(r["name"]) not in known]
    meta["offboard"] = offboard
    print("research names with no match:", sorted({r["name"] for k in ("sleepers", "busts", "breakouts", "rookies") for r in gather(k) if norm(r["name"]) not in known}))
    print("injury research names with no match:", [v["name"] for k, v in inj.items() if k not in espn])

    os.makedirs(os.path.join(ROOT, "web"), exist_ok=True)
    with open(os.path.join(ROOT, "web", "data.js"), "w") as f:
        f.write("window.DRAFT = " + json.dumps(dict(meta=meta, players=players), separators=(",", ":")) + ";\n")
    json.dump(players, open(D("players.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
