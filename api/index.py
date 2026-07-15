"""FastAPI web interface for the GitHub Code Research Agent."""
from __future__ import annotations

import os
import re
import sys
import traceback
from pathlib import Path

import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

app = FastAPI(title="GitHub Code Research Agent", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


CSS = """\
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
.container{max-width:960px;margin:0 auto;padding:30px 20px}
h1{font-size:1.6rem;margin-bottom:4px;color:#58a6ff}
.sub{color:#8b949e;margin-bottom:20px}
.srch{display:flex;gap:8px;margin-bottom:16px}
.srch input{flex:1;padding:10px 14px;background:#161b22;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:1rem;outline:none}
.srch input:focus{border-color:#58a6ff}
.srch button{padding:10px 24px;background:#238636;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:1rem;font-weight:600}
.srch button:disabled{opacity:.5}
.chip{display:inline-block;padding:4px 10px;background:#21262d;border:1px solid #30363d;border-radius:4px;cursor:pointer;font-size:0.82rem;margin:2px;color:#58a6ff}
.chip:hover{background:#30363d;border-color:#58a6ff}
#st{color:#8b949e;margin-bottom:14px;min-height:22px}
#res{display:none}
table{width:100%;border-collapse:collapse;font-size:0.85rem}
th{background:#161b22;padding:10px 12px;text-align:left;font-weight:600;color:#8b949e;border-bottom:1px solid #30363d}
td{padding:10px 12px;border-bottom:1px solid #21262d;vertical-align:top}
tr:hover{background:#161b22}
.rn{color:#58a6ff;font-weight:600;text-decoration:none}
.rn:hover{text-decoration:underline}
.rd{color:#8b949e;font-size:0.8rem;margin-top:2px}
.star{color:#d29922}
.lg{display:inline-block;padding:2px 6px;background:#1f2a36;border-radius:3px;font-size:0.75rem;color:#8b949e}
.ft{text-align:center;color:#484f58;font-size:0.78rem;margin-top:30px;padding-top:20px;border-top:1px solid #21262d}
"""

HTML_PAGE = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>GitHub Code Research Agent</title>
<style>{{CSS}}</style>
</head>
<body>
<div class="container">
<h1>GitHub Code Research Agent</h1>
<p class="sub">输入需求 → 检索开源项目 → 输出推荐技术路径</p>
<div class="srch">
<input id="q" placeholder="例如：建筑立面风格识别的 Python 项目" autofocus>
<button id="btn">Search</button>
</div>
<div>
<span class="chip">YOLOv8</span>
<span class="chip">RAG QA</span>
<span class="chip">Architecture</span>
<span class="chip">DWG</span>
</div>
<div id="st">Ready.</div>
<div id="res"></div>
<div class="ft">Web quick search. Full RAG: python agent.py</div>
</div>
<script>
document.getElementById('btn').onclick = function() {{
  var q = document.getElementById('q').value.trim();
  if (!q) return;
  var btn = document.getElementById('btn');
  var st = document.getElementById('st');
  var res = document.getElementById('res');
  btn.disabled = true;
  st.textContent = 'Searching...';
  res.style.display = 'none';
  var xhr = new XMLHttpRequest();
  xhr.open('GET', '/api/search?q=' + encodeURIComponent(q));
  xhr.onload = function() {{
    btn.disabled = false;
    if (xhr.status !== 200) {{ st.textContent = 'Error: ' + xhr.status; return; }}
    var d = JSON.parse(xhr.responseText);
    if (d.error) {{ st.textContent = 'Error: ' + d.error; return; }}
    render(d);
    st.textContent = 'Found ' + d.candidates + ' repositories.';
  }};
  xhr.onerror = function() {{ btn.disabled = false; st.textContent = 'Network error'; }};
  xhr.send();
}};

var chips = document.querySelectorAll('.chip');
for (var i = 0; i < chips.length; i++) {{
  chips[i].onclick = function() {{
    document.getElementById('q').value = this.textContent;
    document.getElementById('btn').click();
  }};
}}

function render(d) {{
  var repos = d.repos || [];
  var el = document.getElementById('res');
  var html = '';
  if (repos.length === 0) {{
    html = '<p style="color:#484f58;text-align:center;padding:40px">No results.</p>';
  }} else {{
    html = '<table><thead><tr><th style="width:55%">Repository</th><th style="width:12%">Stars</th><th style="width:15%">Language</th></tr></thead><tbody>';
    for (var i = 0; i < repos.length; i++) {{
      var r = repos[i];
      html += '<tr><td><a class="rn" href="' + r.url + '" target="_blank">' + r.name + '</a>';
      if (r.description) html += '<div class="rd">' + r.description + '</div>';
      html += '</td><td><span class="star">★</span> ' + r.stars + '</td><td>' + (r.language||'') + '</td></tr>';
    }}
    html += '</tbody></table>';
  }}
  el.innerHTML = html;
  el.style.display = 'block';
}}
</script>
</body>
</html>"""


def _gh_headers():
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PAT")
    h = {{"Accept": "application/vnd.github+json", "User-Agent": "gh-code-agent"}}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _search_gh(query: str, limit: int = 10) -> list[dict]:
    try:
        resp = requests.get(
            "https://api.github.com/search/repositories",
            headers=_gh_headers(),
            params={{"q": query, "sort": "stars", "order": "desc", "per_page": limit}},
            timeout=30,
        )
        if resp.status_code in (403, 429):
            return []
        resp.raise_for_status()
        return resp.json().get("items", [])
    except Exception:
        return []


def _expand_queries(text: str) -> list[str]:
    t = text.strip()
    queries = [f"{{t}} in:name,description,readme"]
    has_cjk = bool(re.search(r"[一-鿿]", t))
    if any(a in t for a in ["建筑", "立面", "风格", "architecture", "facade", "architectural"]):
        queries.extend(['"architectural style recognition"', '"architecture style classification"',
                        '"building facade classification"', 'architectural style recognition python'])
    if "python" not in t.lower() and not has_cjk:
        queries.append(f"{{t}} language:Python")
        queries.append(f"{{t}} Python")
    seen = set()
    return [q for q in queries if not (q in seen or seen.add(q))]


def _is_relevant(item: dict, original_query: str) -> bool:
    text = f"{{item.get('full_name','')}} {{item.get('description','')}}".lower()
    if any(k in text for k in ["independent", "blog", "买房", "润学", "awesome"]):
        return False
    arch = ["建筑", "立面", "architecture", "facade", "architectural", "building", "style"]
    if any(a in original_query.lower() for a in arch):
        return any(a in text for a in arch) and any(t in text for t in ("classification", "recognition", "识别"))
    return True


def _fmt(item: dict) -> dict:
    return {{"name": item.get("full_name", ""), "url": item.get("html_url", ""),
            "description": (item.get("description") or "")[:200],
            "language": item.get("language") or "", "stars": item.get("stargazers_count", 0),
            "topics": item.get("topics", [])[:5]}}


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML_PAGE


@app.get("/api/search")
async def search(q: str = Query(..., description="Natural language requirement")):
    try:
        queries = _expand_queries(q)
        seen, all_repos = set(), []
        for query in queries[:8]:
            for item in _search_gh(query, 8):
                name = item.get("full_name", "")
                if name and name not in seen:
                    seen.add(name)
                    if _is_relevant(item, q):
                        all_repos.append(_fmt(item))
        all_repos.sort(key=lambda x: x.get("stars", 0), reverse=True)
        return {{"query": q, "candidates": min(len(all_repos), 15), "repos": all_repos[:15]}}
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({{"error": str(e)}}, status_code=500)
