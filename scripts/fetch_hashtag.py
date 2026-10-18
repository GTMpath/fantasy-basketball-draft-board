"""Pull Hashtag Basketball 2026-27 projections for every team (free view caps at 30 rows,
so we post back once per team), with Yahoo position eligibility."""
import re, html, json, time, sys
import requests

URL = "https://hashtagbasketball.com/fantasy-basketball-projections"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
P = "ctl00$ContentPlaceHolder1$"


def form_state(page):
    data = {}
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*>', page):
        tag = m.group(0)
        n = re.search(r'name="([^"]+)"', tag)
        v = re.search(r'value="([^"]*)"', tag)
        if n:
            data[n.group(1)] = html.unescape(v.group(1)) if v else ""
    for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', page, re.S):
        sel = re.search(r'<option selected="selected" value="([^"]*)"', m.group(2))
        if sel:
            data[m.group(1)] = html.unescape(sel.group(1))
    for m in re.finditer(r'<input[^>]*type="checkbox"[^>]*>', page):
        tag = m.group(0)
        if 'checked="checked"' in tag:
            data[re.search(r'name="([^"]+)"', tag).group(1)] = "on"
    return data


def cell(c):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())


def parse(page):
    t = re.search(r'<table class="table table-sm table-bordered table-striped table--statistics.*?</table>', page, re.S)
    out = []
    if not t:
        return out
    for r in re.findall(r"<tr.*?</tr>", t.group(0), re.S):
        tds = re.findall(r"<td.*?</td>", r, re.S)
        if len(tds) < 17:
            continue
        c = [cell(x) for x in tds]
        if not c[0].isdigit():
            continue
        name = re.search(r"<a[^>]*>(.*?)</a>", tds[1], re.S)
        nm = cell(name.group(1)) if name else c[1]
        def pct(s):
            m = re.match(r"([\d.]+)\s*\(([\d.]+)/([\d.]+)\)", s)
            return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else (None, None, None)
        fg, fgm, fga = pct(c[7]); ft, ftm, fta = pct(c[8])
        f = lambda s: float(s) if re.match(r"^-?[\d.]+$", s) else None
        out.append(dict(name=nm, adp_site=f(c[2]), pos=c[3], team=c[4], gp=f(c[5]), mpg=f(c[6]),
                        fg_pct=fg, fgm=fgm, fga=fga, ft_pct=ft, ftm=ftm, fta=fta,
                        tpm=f(c[9]), pts=f(c[10]), reb=f(c[11]), ast=f(c[12]), stl=f(c[13]),
                        blk=f(c[14]), tov=f(c[15]), ht_total=f(c[16])))
    return out


def post(s, page, target, **over):
    d = form_state(page)
    d["__EVENTTARGET"] = P + target
    d["__EVENTARGUMENT"] = ""
    for k, v in over.items():
        d[P + k] = v
    r = s.post(URL, data=d, headers=UA, timeout=60)
    r.raise_for_status()
    return r.text


def main():
    s = requests.Session()
    page = s.get(URL, headers=UA, timeout=60).text
    teams = re.findall(r'<option(?: selected="selected")? value="([A-Z]{2,3})">', re.search(r'name="ctl00\$ContentPlaceHolder1\$DDTSUM".*?</select>', page, re.S).group(0))
    teams = [t for t in teams if t != "All"]
    page = post(s, page, "DDPOSFROM", DDPOSFROM="1")  # Yahoo eligibility
    players = {}
    for t in teams:
        page = post(s, page, "DDTSUM", DDTSUM=t)
        rows = parse(page)
        for r in rows:
            players[r["name"]] = r
        print(t, len(rows), file=sys.stderr)
        time.sleep(1.2)
    json.dump(sorted(players.values(), key=lambda r: -(r["ht_total"] or -99)), open("data/hashtag_projections.json", "w"), indent=1)
    print("players", len(players))


if __name__ == "__main__":
    main()
