# Fantasy basketball draft board (Yahoo H2H 9-cat or 8-cat, 2026-27)

A static draft board for a 12-team, 13-round head-to-head categories league. Open `web/index.html` in a browser. No server needed, and picks are saved in the browser.

During a live draft, click **Taken** on each player another team picks and **Draft** on your own picks. The **Fit** column then scores the players still available against your roster: it weights the categories you are losing, discounts players likely to miss games, allows one injury-risk pick, and marks down anyone who should still be there at your next pick. Set teams, your draft slot, rounds and the 9-cat or 8-cat format in the top bar.

## What is in the data

- `web/data.js` and `data/players.json`: about 280 players with a blended ESPN, Yahoo and Hashtag Basketball projection, per-category z-scores, injury flags (red avoid, orange risk, yellow watch), games-played history, an aging adjustment, a check on players 29+ coming off a jump season, and games during the fantasy playoff weeks (19 to 21).
- `data/research_*.json`: injuries, role changes and sleeper, breakout and bust notes from articles, videos and mock drafts, as of October 18, 2026. Each note links its sources.
- `data/aging.json`, `data/ages.json`, `data/last_season_jump.json`: inputs to the aging and jump-season adjustments, fitted on Basketball Reference history.

## Rebuilding

`scripts/build.py` merges the sources and rebuilds `web/data.js`; `scripts/refresh.sh` re-pulls ESPN projections and Hashtag Basketball, then rebuilds. The Yahoo projections and the league's past draft that the original build used came from a private league and are not in this repo, so a rebuild needs your own `data/yahoo_projections.txt` (format in `build.py`) or runs on ESPN and Hashtag alone.

`scripts/uitest.sh [slot]` simulates a full draft through the real UI as a smoke test.
