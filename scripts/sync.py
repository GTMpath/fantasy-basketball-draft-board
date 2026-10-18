"""Write web/sync.js from the full ordered pick list during a live draft.

usage: python3 scripts/sync.py picks.txt      (one player name per line, overall pick order from pick 1)

Every name is resolved to the board's exact spelling before anything is written: accents and punctuation are ignored,
Jr./Sr./II/III/IV suffixes are optional, common nicknames are expanded, and as a last resort a unique last name plus
first initial is accepted. If any name cannot be resolved, nothing is written and the unresolved names are printed,
so the board never receives a partial list. The version is the current time in milliseconds, so the board only ever
applies a newer file than the last one it saw.
"""
import json, os, re, sys, time, unicodedata

ROOT = os.path.join(os.path.dirname(__file__), "..")
ALIAS = {"herb": "herbert", "cam": "cameron", "nic": "nicolas", "mo": "moritz", "zach": "zachary", "pj": "pj",
         "og": "og", "kj": "kenyon", "bub": "carlton", "nick": "nickeil"}


def norm(x):
    x = unicodedata.normalize("NFD", x).encode("ascii", "ignore").decode().lower()
    x = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", x)
    return re.sub(r"[^a-z ]", "", x).split()


players = [p["name"] for p in json.load(open(os.path.join(ROOT, "data", "players.json")))]
full = {" ".join(norm(n)): n for n in players}


def resolve(raw):
    t = norm(raw)
    if not t:
        return None
    key = " ".join(t)
    if key in full:
        return full[key]
    if t[0] in ALIAS and " ".join([ALIAS[t[0]]] + t[1:]) in full:
        return full[" ".join([ALIAS[t[0]]] + t[1:])]
    # unique last name + first initial ("N. Alexander-Walker", "Cam Johnson")
    hits = [n for k, n in full.items() if k.split()[-1] == t[-1] and k[0] == t[0][0]]
    return hits[0] if len(hits) == 1 else None


names = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip() and not l.startswith("#")]
out, bad = [], []
for n in names:
    r = resolve(n)
    (out.append(r) if r else bad.append(n))
dups = sorted({n for n in out if out.count(n) > 1})
if bad or dups:
    print("NOT WRITTEN.", "Unresolved: " + ", ".join(bad) if bad else "", "Duplicates: " + ", ".join(dups) if dups else "")
    sys.exit(1)
v = int(time.time() * 1000)
open(os.path.join(ROOT, "web", "sync.js"), "w").write("window.SYNC = " + json.dumps({"v": v, "picks": out}) + ";\n")
print(f"wrote {len(out)} picks, v={v}; last 3: {out[-3:]}")
