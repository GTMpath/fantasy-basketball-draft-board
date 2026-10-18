#!/bin/bash
# Re-pull projections, ADP and injury status, then rebuild web/data.js. Run this the morning of the draft.
set -e
cd "$(dirname "$0")/.."
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36'
mkdir -p data/raw
espn() { curl -sf --max-time 120 -A "$UA" -H "X-Fantasy-Filter: $3" -o "data/raw/$2.tmp" "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/$1/segments/0/leaguedefaults/1?view=kona_player_info" && mv "data/raw/$2.tmp" "data/raw/$2"; }
espn 2027 espn_players.json '{"players":{"limit":600,"sortDraftRanks":{"sortPriority":100,"sortAsc":true,"value":"STANDARD"}}}'
for y in 2025 2024; do
  [ -f "data/raw/espn_players_$y.json" ] || espn $y "espn_players_$y.json" '{"players":{"limit":700,"sortPercOwned":{"sortPriority":1,"sortAsc":false}}}'
done
curl -sfL --max-time 60 -A "$UA" -o data/raw/hashtag_adp.tmp https://hashtagbasketball.com/fantasy-basketball-adp && mv data/raw/hashtag_adp.tmp data/raw/hashtag_adp.html
curl -sfL --max-time 60 -A "$UA" -o data/raw/hashtag_proj.tmp https://hashtagbasketball.com/fantasy-basketball-projections && mv data/raw/hashtag_proj.tmp data/raw/hashtag_proj.html
python3 - <<'PY' 2>/dev/null
import sys, json
sys.path.insert(0, "scripts")
import fetch_hashtag as h
rows = h.parse(open("data/raw/hashtag_proj.html", encoding="utf-8", errors="ignore").read())
if rows:
    json.dump(rows, open("data/hashtag_projections.json", "w"), indent=1)
PY
python3 scripts/build.py
# projections changed, so recompute the older-jumper penalty against them, then rebuild
python3 scripts/jump_check.py && python3 scripts/build.py
echo "Done. Open web/index.html (picks already entered are kept)."
