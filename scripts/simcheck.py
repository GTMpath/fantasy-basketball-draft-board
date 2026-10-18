"""Run the in-browser slot simulation headlessly and print average category ranks. usage: python3 scripts/simcheck.py [slots e.g. 3,7,11] [n]"""
import subprocess, os, re, html, sys, tempfile
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
slots = [int(x) for x in (sys.argv[1] if len(sys.argv) > 1 else "3,7,11").split(",")]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 60
prof = os.path.join(tempfile.gettempdir(), "draftboard-simcheck")
for slot in slots:
    url = f"file://{root}/web/index.html#view=slot&slot={slot}" + os.environ.get("TUNE", "") + f"&simrun={n}"
    p = subprocess.Popen(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--headless=new", "--disable-gpu", "--no-first-run", "--user-data-dir=" + prof,
                          "--allow-file-access-from-files", "--virtual-time-budget=90000", "--dump-dom", url], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        out = p.communicate(timeout=150)[0].decode()
    except subprocess.TimeoutExpired:
        p.kill(); out = p.communicate()[0].decode()
    sp = re.search(r'<div id="slotplan".*?<div id="filters"', out, re.S).group(0)
    cats = re.findall(r'<span class="chip"[^>]*>([^<]+) <b>([\d.]+)</b>', sp)
    vals = [float(v) for _, v in cats]
    print(f"slot {slot:>2}: " + "  ".join(f"{html.unescape(c)} {v}" for c, v in cats) + f"  | mean {sum(vals)/len(vals):.2f} worst {max(vals)} top-half cats {sum(v <= 6.5 for v in vals)}")
    if "-v" in sys.argv:
        for card in re.findall(r'<h2>Round (\d+) <b>pick (\d+)</b></h2>(.*?)</tbody>', sp, re.S)[:6]:
            rows = re.findall(r'data-open="[^"]*">([^<]+)</span>.*?<td class="num">(\d+%)</td><td class="num">(\d+%)</td></tr>', card[2], re.S)
            print(f"   R{card[0]} #{card[1]}: " + ", ".join(f"{html.unescape(a)} {c}" for a, b, c in rows[:5]))
