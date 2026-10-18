#!/bin/bash
# Smoke test: simulate a full draft through the real UI, taking the top recommendation each round.
# usage: scripts/uitest.sh [my_slot]
cd "$(dirname "$0")/.." && SP=${TMPDIR:-/tmp}/draftboard-test && mkdir -p "$SP"
cat > web/_test.html <<HTML
<!doctype html><meta charset="utf-8"><body><pre id="out">start</pre><iframe id="f" src="index.html" style="width:1500px;height:900px"></iframe><script>
const o=document.getElementById('out'); let done=false;
document.getElementById('f').onload=()=>{ if(done) return; done=true; const w=document.getElementById('f').contentWindow, d=w.document;
 try{ w.confirm=()=>true; d.getElementById('resetBtn').click(); const sl=d.getElementById('cfgSlot'); sl.value=${1:-6}; sl.dispatchEvent(new w.Event('change'));
  for(let r=0;r<13;r++){ d.getElementById('simBtn').click(); const b=d.querySelector('#recs button[data-draft]'); if(!b){o.textContent+='\\nno rec button round '+r;break;} b.click(); }
  d.getElementById('simBtn').click();
  o.textContent='CLOCK '+d.getElementById('clock').innerText+'\\nROSTER\\n'+[...d.querySelectorAll('#log .m')].reverse().map(x=>x.innerText).join('\\n')+'\\nSLOTS '+d.getElementById('slots').innerText.replace(/\\n+/g,' | ')+'\\nCATS '+d.getElementById('cats').innerText.replace(/\\n+/g,' ')+' :: '+d.getElementById('catNote').innerText+'\\nLOGLEN '+d.getElementById('log').children.length;
  d.getElementById('resetBtn').click();
 }catch(e){o.textContent+='\\nEXC '+e.stack} };
</script>
HTML
( "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --no-first-run --user-data-dir="$SP/profile" --allow-file-access-from-files --virtual-time-budget=5000 --dump-dom "file://$PWD/web/_test.html" > "$SP/dom.html" 2>/dev/null & pid=$!; for i in $(seq 1 30); do sleep 1; kill -0 $pid 2>/dev/null || break; done; kill $pid 2>/dev/null )
rm -f web/_test.html
python3 -c "
import re,html
s=open('$SP/dom.html').read(); print(html.unescape(re.search(r'<pre id=\"out\">(.*?)</pre>',s,re.S).group(1))[:3000])"
