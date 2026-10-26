"""Shorts Stand web UI — stdlib only.

Run:  python3 web.py [--port 8080]
Then open http://localhost:8080

The page posts to /api/generate, polls /api/job/<id> until the pack is
ready, then renders hooks, script beats, voiceover, captions and metadata
with per-file downloads. Generation runs against the local Lemonade server
(same env vars as the CLI: LEMONADE_BASE_URL, LEMONADE_MODEL).
"""

import argparse
import html
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from shorts_stand.client import LemonadeClient
from shorts_stand.pack import generate_pack

FILES = ["script.md", "voiceover.txt", "captions.srt", "metadata.json",
         "raw_model_output.md"]

jobs = {}  # job_id -> {"status": ..., ...}
jobs_lock = threading.Lock()


def _parse_hooks(hooks_text):
    out = []
    for line in hooks_text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[\d]+[.)]\s*", "", line).strip()
        if line:
            out.append(line)
    return out


def _read_pack(outdir):
    data = {}
    for name in FILES:
        path = os.path.join(outdir, name)
        data[name] = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    try:
        meta = json.loads(data["metadata.json"])
    except (json.JSONDecodeError, KeyError):
        meta = {}
    beats = []
    for m in re.finditer(
        r"- \*\*\[(\d{2}:\d{2})-(\d{2}:\d{2})\]\*\* \U0001f3a4 (.*?)  \n"
        r"  \U0001f4ac On-screen: _(.*?)_  \n"
        r"  \U0001f3ac Shot: (.*?)(?:\n|$)", data["script.md"]):
        beats.append({"start": m.group(1), "end": m.group(2), "vo": m.group(3),
                      "text": m.group(4), "shot": m.group(5)})
    return {"meta": meta, "beats": beats, "files": data}


def _run_job(job_id, topic, niche, duration):
    outdir = os.path.join(tempfile.gettempdir(), f"shorts-stand-{job_id}")
    try:
        # 127.0.0.1, not localhost: avoids IPv6 resolution flakiness on some boxes.
        client = LemonadeClient(
            base_url=os.environ.get("LEMONADE_BASE_URL",
                                    "http://127.0.0.1:13305/api/v1"))
        result = generate_pack(topic, niche, duration, client, outdir)
        pack = _read_pack(outdir)
        with jobs_lock:
            jobs[job_id].update({
                "status": "done",
                "topic": topic, "niche": niche, "duration": duration,
                "beats": result["beats"], "title": result["title"],
                "hooks": _parse_hooks(
                    open(os.path.join(outdir, "script.md"), encoding="utf-8")
                    .read().split("## Recommended hook")[1]
                    .split("## Script")[0]) if "## Recommended hook" in
                open(os.path.join(outdir, "script.md"), encoding="utf-8").read() else [],
                "script_beats": pack["beats"],
                "meta": pack["meta"],
                "voiceover": pack["files"]["voiceover.txt"],
                "srt": pack["files"]["captions.srt"],
            })
    except Exception as e:  # noqa: BLE001 — surface to UI
        with jobs_lock:
            jobs[job_id].update({"status": "error", "error": str(e)})
        shutil.rmtree(outdir, ignore_errors=True)


PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shorts Stand 🍋 — local-AI pre-production studio</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;background:#0e0f13;color:#e8e9ec;
  margin:0;padding:24px;max-width:960px;margin-inline:auto}
h1{font-size:1.6rem;margin:0 0 4px}
.sub{color:#9aa0ad;margin:0 0 20px;font-size:.95rem}
.card{background:#16181e;border:1px solid #262a35;border-radius:12px;padding:18px;margin-bottom:16px}
label{display:block;font-size:.8rem;color:#9aa0ad;margin:10px 0 4px}
input,select{width:100%;padding:10px 12px;border-radius:8px;border:1px solid #2c313d;
  background:#0e0f13;color:#e8e9ec;font-size:1rem}
.row{display:grid;grid-template-columns:2fr 1fr;gap:12px}
button{background:#f5c518;border:0;color:#111;font-weight:700;font-size:1rem;
  padding:12px 20px;border-radius:10px;cursor:pointer;margin-top:14px;width:100%}
button:disabled{opacity:.5;cursor:wait}
.beat{border-left:3px solid #f5c518;padding:8px 12px;margin:10px 0;background:#101218;border-radius:0 8px 8px 0}
.beat .ts{font-family:monospace;color:#f5c518;font-size:.85rem}
.beat .vo{margin:4px 0}
.beat .meta{font-size:.85rem;color:#9aa0ad}
.hook{background:#101218;border:1px solid #262a35;border-radius:8px;padding:10px 12px;margin:8px 0}
pre{background:#0a0b0e;border:1px solid #262a35;border-radius:8px;padding:12px;
  overflow:auto;max-height:320px;font-size:.85rem;white-space:pre-wrap}
.tag{display:inline-block;background:#23262f;border-radius:20px;padding:3px 12px;margin:3px 4px 3px 0;font-size:.85rem}
.dl{display:inline-block;margin:4px 8px 4px 0;font-size:.9rem;color:#f5c518}
#status{color:#9aa0ad;font-size:.9rem;margin-top:8px}
.spin{display:inline-block;width:14px;height:14px;border:2px solid #444;border-top-color:#f5c518;
  border-radius:50%;animation:s 1s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes s{to{transform:rotate(360deg)}}
h2{font-size:1.15rem;margin:0 0 8px}
.err{color:#ff7a7a}
</style></head><body>
<h1>Shorts Stand 🍋</h1>
<p class="sub">Local-AI pre-production studio for short-form video · powered by Lemonade</p>
<div class="card">
  <label>Video topic</label>
  <input id="topic" placeholder="e.g. 5 side hustles with no money" value="5 side hustles with no money">
  <div class="row">
    <div><label>Niche / audience</label>
      <input id="niche" placeholder="e.g. personal finance beginners" value="personal finance beginners"></div>
    <div><label>Duration (sec)</label>
      <input id="duration" type="number" value="45" min="10" max="180"></div>
  </div>
  <button id="go" onclick="generate()">Generate pack</button>
  <div id="status"></div>
</div>
<div id="out"></div>
<script>
const $=id=>document.getElementById(id);
const esc=s=>s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function generate(){
  const topic=$('topic').value.trim();
  if(!topic){$('status').innerHTML='<span class="err">Enter a topic first.</span>';return;}
  $('go').disabled=true;
  $('out').innerHTML='';
  $('status').innerHTML='<span class="spin"></span>Asking the local model… (a 4B model takes a few minutes)';
  let r=await fetch('/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({topic,niche:$('niche').value,duration:parseInt($('duration').value)||45})});
  const {job_id}=await r.json();
  const t0=Date.now();
  while(true){
    await new Promise(r=>setTimeout(r,3000));
    let j=await (await fetch('/api/job/'+job_id)).json();
    const el=Math.round((Date.now()-t0)/1000);
    if(j.status==='running'){$('status').innerHTML='<span class="spin"></span>Generating… '+el+'s elapsed';continue;}
    $('go').disabled=false;
    if(j.status==='error'){$('status').innerHTML='<span class="err">Error: '+esc(j.error)+'</span>';return;}
    $('status').textContent='Done in '+el+'s · '+j.beats+' beats';
    render(j,job_id);return;
  }
}
function render(j,id){
  const dl=f=>'<a class="dl" href="/api/download/'+id+'/'+f+'">⬇ '+f+'</a>';
  let h='<div class="card"><h2>🎣 Hooks</h2>'+j.hooks.map(x=>'<div class="hook">'+esc(x)+'</div>').join('')+'</div>';
  h+='<div class="card"><h2>🎬 Script — '+esc(j.title||'')+'</h2>'+
    j.script_beats.map(b=>'<div class="beat"><div class="ts">'+b.start+' → '+b.end+'</div>'+
      '<div class="vo">🎤 '+esc(b.vo)+'</div>'+
      '<div class="meta">💬 '+esc(b.text)+'<br>🎥 '+esc(b.shot)+'</div></div>').join('')+'</div>';
  h+='<div class="card"><h2>🎙 Voiceover</h2><pre>'+esc(j.voiceover)+'</pre></div>';
  h+='<div class="card"><h2>💬 Captions (SRT)</h2><pre>'+esc(j.srt)+'</pre></div>';
  const m=j.meta||{};
  h+='<div class="card"><h2>📦 Metadata</h2><p><b>'+esc(m.title||'')+'</b></p><p>'+esc(m.description||'')+'</p>'+
    '<p>'+(m.hashtags||[]).map(t=>'<span class="tag">#'+esc(t)+'</span>').join('')+'</p>'+
    (m.pinned_comment?'<p>📌 '+esc(m.pinned_comment)+'</p>':'')+'</div>';
  h+='<div class="card"><h2>⬇ Downloads</h2>'+['script.md','voiceover.txt','captions.srt','metadata.json','raw_model_output.md'].map(dl).join('')+'</div>';
  $('out').innerHTML=h;
}
// Demo hook: ?autostart=1[&topic=..&niche=..&duration=..] fills the form and
// submits on load — handy for screen recordings.
(function(){const q=new URLSearchParams(location.search);if(q.has('autostart')){
  if(q.get('topic'))$('topic').value=q.get('topic');
  if(q.get('niche'))$('niche').value=q.get('niche');
  if(q.get('duration'))$('duration').value=q.get('duration');
  generate();}})();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "ShortsStand/1.0"

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, PAGE)
        parts = u.path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "job":
            with jobs_lock:
                job = jobs.get(parts[2])
            if not job:
                return self._json(404, {"error": "unknown job"})
            safe = {k: v for k, v in job.items() if k != "outdir"}
            return self._json(200, safe)
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "download":
            job_id, fname = parts[2], parts[3]
            if fname not in FILES or not re.fullmatch(r"[0-9a-f-]{36}", job_id):
                return self._json(400, {"error": "bad request"})
            path = os.path.join(tempfile.gettempdir(), f"shorts-stand-{job_id}", fname)
            if not os.path.exists(path):
                return self._json(404, {"error": "not found"})
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/generate":
            return self._json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            topic = str(payload.get("topic", "")).strip()
            if not topic:
                return self._json(400, {"error": "topic is required"})
            niche = str(payload.get("niche", "") or "general audience").strip()
            duration = max(10, min(180, int(payload.get("duration", 45))))
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "invalid JSON payload"})
        job_id = str(uuid.uuid4())
        with jobs_lock:
            jobs[job_id] = {"status": "running", "started": time.time()}
        t = threading.Thread(target=_run_job, args=(job_id, topic, niche, duration),
                             daemon=True)
        t.start()
        # prune old jobs
        with jobs_lock:
            for jid, j in list(jobs.items()):
                if j.get("status") in ("done", "error") and time.time() - j.get("started", 0) > 3600:
                    shutil.rmtree(os.path.join(tempfile.gettempdir(), f"shorts-stand-{jid}"),
                                  ignore_errors=True)
                    del jobs[jid]
        return self._json(200, {"job_id": job_id})

    def log_message(self, *a):
        pass  # quiet


def main(argv=None):
    p = argparse.ArgumentParser(description="Shorts Stand web UI")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args(argv)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Shorts Stand UI: http://127.0.0.1:{args.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
