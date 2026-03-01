#!/usr/bin/env python3
"""
OrgaFlow — Demo Web Server
===========================
Launches a local web interface for live demonstration of the SEO pipeline.

Usage:
    python demo_server.py
    # Opens http://localhost:8000 automatically
"""
import os
import sys
import re
import json
import asyncio
import sqlite3
import threading
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
import uvicorn

app = FastAPI(title="OrgaFlow Demo", docs_url=None, redoc_url=None)

SAMPLE_URLS = "https://www.shopify.com/es/\nhttps://www.salesforce.com/es/\nhttps://kinsta.com/es/\nhttps://woocommerce.com/\nhttps://yoast.com/"


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[mGKHF]|\x1b\[.*?[@-~]|\x1b\].*?\x07", "", text)


def get_db_stats() -> dict:
    db = BASE_DIR / "data" / "pipeline.db"
    if not db.exists():
        return {}
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT status, COUNT(*) FROM pipeline_runs GROUP BY status").fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


def get_articles(limit: int = 30) -> list:
    db = BASE_DIR / "data" / "pipeline.db"
    if not db.exists():
        return []
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        """SELECT url, article_type, hub, article_title, status, anchor_text, scheduled_at
           FROM pipeline_runs
           WHERE status IN ('published','dry_run')
           ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [
        {"url": r[0], "type": r[1], "hub": r[2], "title": r[3],
         "status": r[4], "anchor": r[5], "scheduled": r[6]}
        for r in rows
    ]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    stats = get_db_stats()
    total = sum(stats.values())
    generated = stats.get("published", 0) + stats.get("dry_run", 0)
    articles = get_articles()
    articles_html = _build_articles_html(articles)
    return _build_page(total, generated, articles_html)


@app.get("/run")
async def run_stream(urls: str = ""):
    async def generate():
        yield "data: OrgaFlow Pipeline Starting...\n\n"

        if urls.strip():
            url_list = [u.strip() for u in urls.splitlines() if u.strip().startswith("http")]
            temp_csv = BASE_DIR / "data" / "demo_input.csv"
            temp_csv.write_text("url\n" + "\n".join(url_list) + "\n", encoding="utf-8")
            csv_arg = str(temp_csv)
        else:
            csv_arg = str(BASE_DIR / "data" / "sample_urls.csv")

        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1", "TERM": "dumb"}

        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(BASE_DIR / "pipeline.py"), csv_arg, "--dry-run",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = strip_ansi(line.decode("utf-8", errors="replace")).rstrip()
            # Skip empty lines and pure box-drawing characters
            clean = re.sub(r"[─│┌┐└┘├┤┬┴┼╴╵╶╷╸╹╺╻]+", "", text).strip()
            if clean:
                yield f"data: {text}\n\n"

        await proc.wait()
        yield "data: \n\n"
        yield "data: Pipeline finished.\n\n"
        yield "data: DONE\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/report", response_class=HTMLResponse)
async def latest_report():
    reports = sorted(BASE_DIR.glob("reports/report_*.html"), reverse=True)
    if reports:
        return reports[0].read_text(encoding="utf-8")
    return "<h1 style='color:white;padding:60px;background:#0f1117;font-family:system-ui'>No report yet — run the pipeline first.</h1>"


@app.get("/articles")
async def articles_json():
    return JSONResponse(get_articles())


# ── HTML builders ─────────────────────────────────────────────────────────────

def _build_articles_html(articles: list) -> str:
    if not articles:
        return "<p style='color:#6b7280;text-align:center;padding:48px 0'>Run the pipeline to see generated articles here.</p>"

    color_map = {"pillar": "#3b82f6", "commercial": "#22c55e", "faq": "#f59e0b"}
    rows = ""
    for a in articles[:18]:
        c = color_map.get(a["type"], "#6b7280")
        url_short = (a["url"][:52] + "…") if len(a["url"]) > 52 else a["url"]
        title = (a["title"] or "Untitled")[:80]
        sched = a["scheduled"][:10] if a.get("scheduled") else "—"
        rows += f"""
        <div class="article-card">
          <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px">
            <span style="background:{c};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700">{a["type"].upper()}</span>
            <span style="color:#6b7280;font-size:12px">{a["hub"] or "—"}</span>
            <span style="margin-left:auto;color:#6b7280;font-size:11px">{sched}</span>
          </div>
          <div style="font-weight:600;color:#e0e0e0;margin-bottom:4px;font-size:14px">{title}</div>
          <div style="font-size:12px;color:#9ca3af">
            <a href="{a["url"]}" target="_blank" style="color:#7eb8f7">{url_short}</a>
            &nbsp;·&nbsp; anchor: <em style="color:#c9d1d9">{a["anchor"] or "—"}</em>
          </div>
        </div>"""
    return rows


def _build_page(total: int, generated: int, articles_html: str) -> str:
    # Build the full HTML page (no .format() to avoid JS brace escaping issues)
    page = _HTML_TEMPLATE
    page = page.replace("__TOTAL__", str(total))
    page = page.replace("__GENERATED__", str(generated))
    page = page.replace("__SAMPLE_URLS__", SAMPLE_URLS)
    page = page.replace("__ARTICLES_HTML__", articles_html)
    return page


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>OrgaFlow — Demo</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #0f1117; color: #e0e0e0; font-family: system-ui, -apple-system, sans-serif; }

    .header { background: linear-gradient(135deg,#0f1117,#1a1d27); border-bottom: 1px solid #2d3148;
               padding: 18px 32px; display: flex; align-items: center; gap: 14px; }
    .logo { font-size: 1.55rem; font-weight: 800; color: #7eb8f7; letter-spacing: -.5px; }
    .badge { background: #1e3a5f; color: #7eb8f7; padding: 3px 10px; border-radius: 20px;
             font-size: 11px; font-weight: 700; border: 1px solid #2d5a8e; }
    .subtitle { color: #6b7280; font-size: 13px; margin-left: auto; }

    .wrap { max-width: 1280px; margin: 0 auto; padding: 28px 24px; }

    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr));
             gap: 14px; margin-bottom: 28px; }
    .stat { background: #1a1d27; border: 1px solid #2d3148; border-radius: 10px;
            padding: 18px; text-align: center; }
    .stat-v { font-size: 2rem; font-weight: 700; }
    .stat-l { color: #6b7280; font-size: 12px; margin-top: 3px; }

    .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; margin-bottom: 22px; }
    @media(max-width:760px) { .cols { grid-template-columns: 1fr; } }

    .card { background: #1a1d27; border: 1px solid #2d3148; border-radius: 10px; overflow: hidden; }
    .ch { padding: 14px 18px; border-bottom: 1px solid #2d3148; font-weight: 600;
          color: #c9d1d9; display: flex; align-items: center; justify-content: space-between; }
    .cb { padding: 18px; }

    textarea { width: 100%; background: #0a0d13; border: 1px solid #2d3148; border-radius: 6px;
               color: #e0e0e0; padding: 11px 13px; font-family: monospace; font-size: 13px;
               resize: vertical; outline: none; line-height: 1.6; }
    textarea:focus { border-color: #3b82f6; }

    .btn { padding: 9px 22px; border-radius: 6px; font-weight: 600; cursor: pointer;
           border: none; font-size: 14px; transition: background .15s; }
    .btn-p { background: #3b82f6; color: #fff; }
    .btn-p:hover { background: #2563eb; }
    .btn-p:disabled { background: #1e3a5f; color: #6b7280; cursor: not-allowed; }
    .btn-o { background: transparent; color: #7eb8f7; border: 1px solid #2d5a8e; }
    .btn-o:hover { background: #1e3a5f; }

    .terminal { background: #07090e; border-radius: 6px; padding: 14px 16px;
                font-family: 'Courier New', monospace; font-size: 12.5px; line-height: 1.65;
                height: 390px; overflow-y: auto; white-space: pre-wrap; word-break: break-all;
                border: 1px solid #1a1d27; color: #9ca3af; }
    .tok-ok { color: #22c55e; }
    .tok-warn { color: #f59e0b; }
    .tok-info { color: #7eb8f7; }
    .tok-head { color: #a855f7; font-weight: bold; }
    .tok-prompt { color: #22c55e; }

    .pbar { height: 3px; background: #2d3148; border-radius: 2px; overflow: hidden; margin-top: 10px; }
    .pfill { height: 100%; background: linear-gradient(90deg,#3b82f6,#7eb8f7);
             width: 0; transition: width .4s; border-radius: 2px; }

    .anchor-row { display: flex; height: 10px; border-radius: 5px; overflow: hidden; margin: 12px 0 8px; }
    .anchor-seg { height: 100%; transition: width .6s ease; }
    .anchor-leg { display: flex; gap: 14px; flex-wrap: wrap; }
    .anchor-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #9ca3af; }
    .anchor-dot { width: 9px; height: 9px; border-radius: 50%; }

    .article-card { background: #0f1117; border: 1px solid #2d3148; border-radius: 8px;
                    padding: 14px 16px; margin-bottom: 10px; }
    .article-card:hover { border-color: #3b82f6; }
    .articles-grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(340px,1fr)); gap: 10px; }

    a { color: #7eb8f7; text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>

<div class="header">
  <span class="logo">OrgaFlow</span>
  <span class="badge">DEMO</span>
  <span class="subtitle">SEO Content Pipeline &amp; Editorial Hub Network</span>
</div>

<div class="wrap">

  <!-- Stats bar -->
  <div class="stats">
    <div class="stat">
      <div class="stat-v" style="color:#7eb8f7">5</div>
      <div class="stat-l">Editorial Hubs</div>
    </div>
    <div class="stat">
      <div class="stat-v" style="color:#22c55e">3</div>
      <div class="stat-l">Articles / URL</div>
    </div>
    <div class="stat">
      <div class="stat-v" style="color:#a855f7" id="statTotal">__TOTAL__</div>
      <div class="stat-l">Pipeline Runs</div>
    </div>
    <div class="stat">
      <div class="stat-v" style="color:#f59e0b" id="statGen">__GENERATED__</div>
      <div class="stat-l">Articles Generated</div>
    </div>
    <div class="stat">
      <div class="stat-v" style="color:#22c55e">2,000+</div>
      <div class="stat-l">Max Scale (URLs)</div>
    </div>
  </div>

  <div class="cols">

    <!-- Left column -->
    <div>
      <!-- Run panel -->
      <div class="card" style="margin-bottom:20px">
        <div class="ch">
          Run Pipeline
          <a href="/report" target="_blank" class="btn btn-o" style="padding:5px 13px;font-size:12px">View Report</a>
        </div>
        <div class="cb">
          <label style="color:#9ca3af;font-size:12px;display:block;margin-bottom:7px">URLs to process (one per line):</label>
          <textarea id="urlInput" rows="7">__SAMPLE_URLS__</textarea>
          <div style="margin-top:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
            <button class="btn btn-p" id="runBtn" onclick="runPipeline()">&#9654; Run Pipeline</button>
            <button class="btn btn-o" onclick="clearTerm()">Clear</button>
            <span id="statusTxt" style="font-size:12px;color:#6b7280"></span>
          </div>
          <div class="pbar"><div class="pfill" id="pf"></div></div>
        </div>
      </div>

      <!-- Anchor model -->
      <div class="card">
        <div class="ch">
          Anchor Distribution Model
          <span style="font-size:11px;color:#6b7280">Dirichlet &alpha;=[6,4,6,4]</span>
        </div>
        <div class="cb">
          <div class="anchor-row">
            <div class="anchor-seg" id="sBrand"   style="background:#3b82f6;width:30%"></div>
            <div class="anchor-seg" id="sExact"   style="background:#22c55e;width:20%"></div>
            <div class="anchor-seg" id="sPartial" style="background:#f59e0b;width:30%"></div>
            <div class="anchor-seg" id="sGeneric" style="background:#6b7280;width:20%"></div>
          </div>
          <div class="anchor-leg">
            <div class="anchor-item"><div class="anchor-dot" style="background:#3b82f6"></div><span id="lBrand">Brand 30%</span></div>
            <div class="anchor-item"><div class="anchor-dot" style="background:#22c55e"></div><span id="lExact">Exact URL 20%</span></div>
            <div class="anchor-item"><div class="anchor-dot" style="background:#f59e0b"></div><span id="lPartial">Partial 30%</span></div>
            <div class="anchor-item"><div class="anchor-dot" style="background:#6b7280"></div><span id="lGeneric">Generic 20%</span></div>
          </div>
          <p style="font-size:11px;color:#6b7280;margin-top:12px;line-height:1.6">
            Each URL receives an independent stochastic draw. The aggregate distribution
            is statistically indistinguishable from an organic backlink profile.
            Over-optimisation alerts trigger if Brand &gt; 40% or Exact URL &gt; 30%.
          </p>
        </div>
      </div>
    </div>

    <!-- Right column: live terminal -->
    <div class="card">
      <div class="ch">
        Live Output
        <span style="font-size:11px;color:#6b7280" id="termStatus">Idle</span>
      </div>
      <div class="cb" style="padding:12px">
        <div class="terminal" id="term"><span class="tok-prompt">$&nbsp;</span><span class="tok-info">Ready &mdash; click "Run Pipeline" to start the demo.</span></div>
      </div>
    </div>

  </div>

  <!-- Generated Articles -->
  <div class="card">
    <div class="ch">
      Generated Articles
      <span style="font-size:12px;color:#6b7280">Pillar &nbsp;/&nbsp; Commercial &nbsp;/&nbsp; FAQ &mdash; each with H1&ndash;H3 structure + schema markup</span>
    </div>
    <div class="cb">
      <div class="articles-grid" id="articlesGrid">
        __ARTICLES_HTML__
      </div>
    </div>
  </div>

</div><!-- /wrap -->

<script>
  var evtSrc = null;

  function runPipeline() {
    var btn    = document.getElementById('runBtn');
    var term   = document.getElementById('term');
    var urls   = document.getElementById('urlInput').value;
    var status = document.getElementById('statusTxt');
    var ts     = document.getElementById('termStatus');
    var pf     = document.getElementById('pf');

    btn.disabled = true;
    btn.textContent = 'Running...';
    status.textContent = 'Processing…';
    status.style.color = '#f59e0b';
    ts.textContent = 'Running';
    ts.style.color = '#f59e0b';
    pf.style.width = '4%';
    term.innerHTML = '<span class="tok-prompt">$ </span><span class="tok-info">python pipeline.py --dry-run</span>\n\n';

    if (evtSrc) { evtSrc.close(); }

    evtSrc = new EventSource('/run?urls=' + encodeURIComponent(urls));
    var pct = 4;

    evtSrc.onmessage = function(e) {
      var line = e.data;

      if (line === 'DONE') {
        evtSrc.close();
        btn.disabled = false;
        btn.textContent = '\u25B6 Run Pipeline';
        status.textContent = 'Complete';
        status.style.color = '#22c55e';
        ts.textContent = 'Done';
        ts.style.color = '#22c55e';
        pf.style.width = '100%';
        setTimeout(function() { pf.style.width = '0'; }, 2000);
        refreshArticles();
        animateAnchors();
        return;
      }

      var cls = '';
      if (/OK|DRY|idempotency/.test(line))           cls = 'tok-ok';
      else if (/WARN|failed|Error|error/.test(line))  cls = 'tok-warn';
      else if (/===|Pipeline|Starting/.test(line))    cls = 'tok-head';
      else if (/Brand:|Exact|Partial|Generic|Anchor|Report|Dirichlet/.test(line)) cls = 'tok-info';

      var span = cls
        ? '<span class="' + cls + '">' + esc(line) + '</span>'
        : esc(line);
      term.innerHTML += span + '\n';
      term.scrollTop = term.scrollHeight;

      pct = Math.min(93, pct + 1.8);
      pf.style.width = pct + '%';
    };

    evtSrc.onerror = function() {
      evtSrc.close();
      btn.disabled = false;
      btn.textContent = '\u25B6 Run Pipeline';
      status.textContent = 'Connection error';
      status.style.color = '#ef4444';
      ts.textContent = 'Error';
    };
  }

  function esc(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function clearTerm() {
    document.getElementById('term').innerHTML =
      '<span class="tok-prompt">$ </span><span class="tok-info">Cleared.</span>\n';
  }

  function refreshArticles() {
    fetch('/articles').then(function(r){ return r.json(); }).then(function(data) {
      var colors = { pillar:'#3b82f6', commercial:'#22c55e', faq:'#f59e0b' };
      var grid = document.getElementById('articlesGrid');
      if (!data.length) return;
      grid.innerHTML = data.slice(0, 18).map(function(a) {
        var c  = colors[a.type] || '#6b7280';
        var u  = a.url.length > 52 ? a.url.substring(0,52)+'...' : a.url;
        var t  = (a.title || 'Untitled').substring(0, 80);
        var sc = a.scheduled ? a.scheduled.substring(0,10) : '&mdash;';
        return '<div class="article-card">'
          + '<div style="display:flex;gap:8px;align-items:center;margin-bottom:6px">'
          + '<span style="background:'+c+';color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700">'+a.type.toUpperCase()+'</span>'
          + '<span style="color:#6b7280;font-size:12px">'+(a.hub||'&mdash;')+'</span>'
          + '<span style="margin-left:auto;color:#6b7280;font-size:11px">'+sc+'</span>'
          + '</div>'
          + '<div style="font-weight:600;color:#e0e0e0;margin-bottom:4px;font-size:13px">'+esc(t)+'</div>'
          + '<div style="font-size:12px;color:#9ca3af">'
          + '<a href="'+a.url+'" target="_blank" style="color:#7eb8f7">'+esc(u)+'</a>'
          + ' &nbsp;&middot;&nbsp; anchor: <em style="color:#c9d1d9">'+esc(a.anchor||'&mdash;')+'</em>'
          + '</div>'
          + '</div>';
      }).join('');
    });
  }

  function animateAnchors() {
    // Simulate a fresh Dirichlet draw for visual effect
    var raw = [22+Math.random()*16, 13+Math.random()*12, 22+Math.random()*16, 13+Math.random()*12];
    var sum = raw.reduce(function(a,b){return a+b;}, 0);
    var p   = raw.map(function(v){ return (v/sum*100).toFixed(1); });
    var ids = ['sBrand','sExact','sPartial','sGeneric'];
    var lids= ['lBrand','lExact','lPartial','lGeneric'];
    var lbls= ['Brand','Exact URL','Partial','Generic'];
    for (var i=0;i<4;i++) {
      document.getElementById(ids[i]).style.width  = p[i]+'%';
      document.getElementById(lids[i]).textContent = lbls[i]+' '+p[i]+'%';
    }
  }
</script>
</body>
</html>"""


if __name__ == "__main__":
    def _open_browser():
        time.sleep(1.8)
        webbrowser.open("http://localhost:8000")

    threading.Thread(target=_open_browser, daemon=True).start()
    print("\n  OrgaFlow Demo")
    print("  Running at: http://localhost:8000")
    print("  Press Ctrl+C to stop.\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
