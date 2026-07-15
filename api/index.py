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


def _gh_headers():
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PAT")
    h = {"Accept": "application/vnd.github+json", "User-Agent": "gh-code-agent"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _search_gh(query: str, limit: int = 10) -> list[dict]:
    try:
        resp = requests.get(
            "https://api.github.com/search/repositories",
            headers=_gh_headers(),
            params={"q": query, "sort": "stars", "order": "desc", "per_page": limit},
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
    queries = [f"{t} in:name,description,readme"]
    has_cjk = bool(re.search(r"[一-鿿]", t))
    if any(a in t for a in ["建筑", "立面", "风格", "architecture", "facade", "architectural"]):
        queries.extend(['"architectural style recognition"', '"architecture style classification"',
                        '"building facade classification"', 'architectural style recognition python',
                        f"{t} language:Python"])
    if "python" not in t.lower() and not has_cjk:
        queries.append(f"{t} language:Python")
        queries.append(f"{t} Python")
    seen = set()
    return [q for q in queries if not (q in seen or seen.add(q))]


def _is_relevant(item: dict, original_query: str) -> bool:
    text = f"{item.get('full_name','')} {item.get('description','')}".lower()
    if any(k in text for k in ["独立开发者", "独立博客", "博客列表", "买房", "润学"]):
        return False
    arch = ["建筑", "立面", "architecture", "facade", "architectural", "building", "style classification"]
    if any(a in original_query.lower() for a in arch):
        return any(a in text for a in arch) and any(t in text for t in ("classification", "recognition", "识别", "分类"))
    return True


def _fmt(item: dict) -> dict:
    return {"name": item.get("full_name", ""), "url": item.get("html_url", ""),
            "description": (item.get("description") or "")[:200],
            "language": item.get("language") or "", "stars": item.get("stargazers_count", 0),
            "topics": item.get("topics", [])[:5]}


@app.get("/", response_class=HTMLResponse)
async def root():
    return PAGE


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
        return {"query": q, "candidates": min(len(all_repos), 15), "repos": all_repos[:15]}
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


CSS = """\
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
.container{max-width:960px;margin:0 auto;padding:30px 20px}
h1{font-size:1.6rem;margin-bottom:4px;color:#58a6ff}
.sub{color:#8b949e;margin-bottom:20px;font-size:0.9rem}
.srch{display:flex;gap:8px;margin-bottom:16px}
.srch input{flex:1;padding:10px 14px;background:#161b22;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:1rem;outline:none}
.srch input:focus{border-color:#58a6ff}
.srch button{padding:10px 24px;background:#238636;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:1rem;font-weight:600}
.srch button:hover{background:#2ea043}
.srch button:disabled{opacity:.5}
.chip{display:inline-block;padding:4px 10px;background:#21262d;border:1px solid #30363d;border-radius:4px;cursor:pointer;font-size:0.82rem;margin:2px 4px 2px 0;color:#58a6ff}
.chip:hover{background:#30363d;border-color:#58a6ff}
#st{color:#8b949e;font-size:0.88rem;margin-bottom:14px;min-height:22px}
#res{display:none;margin-top:8px}
table{width:100%;border-collapse:collapse;font-size:0.85rem}
th{background:#161b22;padding:10px 12px;text-align:left;font-weight:600;color:#8b949e;border-bottom:1px solid #30363d}
td{padding:10px 12px;border-bottom:1px solid #21262d;vertical-align:top}
tr:hover{background:#161b22}
.rn{color:#58a6ff;font-weight:600;text-decoration:none}
.rn:hover{text-decoration:underline}
.rd{color:#8b949e;font-size:0.8rem;margin-top:2px}
.star{color:#d29922}
.lg{display:inline-block;padding:2px 6px;background:#1f2a36;border-radius:3px;font-size:0.75rem;color:#8b949e}
.tp{display:inline-block;padding:1px 6px;background:#1f2a36;border-radius:10px;font-size:0.72rem;color:#58a6ff;margin:1px 2px}
.tc{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:20px}
.tc h3{color:#58a6ff;font-size:1rem;margin-bottom:12px}
.tpstep{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.tps{background:#1c2333;border:1px solid #30363d;border-radius:6px;padding:8px 14px;text-align:center;flex:1;min-width:120px}
.tps .l{font-size:0.75rem;color:#8b949e}
.tps .v{font-size:0.85rem;color:#c9d1d9;font-weight:500}
.td{color:#8b949e;font-size:0.82rem;line-height:1.6;margin-top:8px}
.fw{display:flex;gap:12px;flex-wrap:wrap;margin-top:12px}
.fi{background:#1c2333;border:1px solid #30363d;border-radius:6px;padding:12px 16px;flex:1;min-width:200px}
.fi .fn{color:#58a6ff;font-size:0.85rem;font-weight:600}
.fi .fs{color:#d29922;font-size:0.8rem}
.fi .fd{color:#8b949e;font-size:0.78rem;margin-top:4px}
.ft{text-align:center;color:#484f58;font-size:0.78rem;margin-top:30px;padding-top:20px;border-top:1px solid #21262d}
"""

INDEX_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>GitHub Code Research Agent</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
<h1>GitHub Code Research Agent</h1>
<p class="sub">输入需求 → 检索开源项目 → 输出推荐技术路径</p>
<div class="srch">
<input id="q" placeholder="例如：建筑立面风格识别的 Python 项目" autofocus>
<button id="btn" onclick="doSearch()">Search</button>
</div>
<div>
<span class="chip" onclick="setQ('YOLOv8 object detection Python')">YOLOv8</span>
<span class="chip" onclick="setQ('RAG document QA Python')">RAG QA</span>
<span class="chip" onclick="setQ('architectural style recognition Python')">Architecture</span>
<span class="chip" onclick="setQ('DWG floor plan parser Python')">DWG</span>
</div>
<div id="st"></div>
<div id="res"></div>
<div class="ft">Web quick search. Full RAG: python agent.py &quot;your requirement&quot;</div>
</div>
<script>
function setQ(v){document.getElementById('q').value=v;doSearch()}
function doSearch(){
  var q=document.getElementById('q').value.trim();
  if(!q)return;
  var btn=document.getElementById('btn');
  var st=document.getElementById('st');
  var res=document.getElementById('res');
  btn.disabled=true;
  st.textContent='Searching...';
  res.style.display='none';
  var xhr=new XMLHttpRequest();
  xhr.open('GET','/api/search?q='+encodeURIComponent(q),true);
  xhr.onload=function(){
    btn.disabled=false;
    if(xhr.status!==200){st.textContent='Error: '+xhr.status;return;}
    var d=JSON.parse(xhr.responseText);
    if(d.error){st.textContent='Error: '+d.error;return;}
    render(d,q);
    st.textContent='Found '+d.candidates+' repos.';
  };
  xhr.onerror=function(){btn.disabled=false;st.textContent='Network error';};
  xhr.send();
}
function render(d,q){
  var repos=d.repos||[];
  var el=document.getElementById('res');
  var arch=/建筑|立面|architecture|facade|architectural|style.*(recog|classif)/i.test(q);
  var html='';
  if(arch){
    html+='<div class="tc"><h3>Recommended: Architectural Style Recognition</h3>';
    html+='<div class="tpstep">';
    html+='<div class="tps"><div class="l">Feature Extractor</div><div class="v">ResNet-50</div></div>';
    html+='<div class="tps"><div class="l">Training</div><div class="v">Transfer Learning</div></div>';
    html+='<div class="tps"><div class="l">Data</div><div class="v">Street View</div></div>';
    html+='<div class="tps"><div class="l">Framework</div><div class="v">PyTorch</div></div>';
    html+='</div>';
    html+='<div class="td">Transfer learning (ResNet-50 pre-trained). Fine-tune on facade images. Data augmentation for lighting variance.</div>';
    html+='<div class="fw">';
    html+='<div class="fi"><div class="fn">dumitrux/architectural-style-recognition</div><div class="fs">★ 31</div><div class="fd">CNN + fastai, 25 styles, Jupyter</div></div>';
    html+='<div class="fi"><div class="fn">AKASH2907/indian_landmark_recognition</div><div class="fs">★ 7</div><div class="fd">CNN + KNN, Python+Keras</div></div>';
    html+='</div></div>';
  }
  if(repos.length===0){
    html+='<table><thead><tr><th>Repository</th><th>Stars</th><th>Language</th></tr></thead><tbody><tr><td colspan="3" style="text-align:center;padding:40px;color:#484f58">No results.</td></tr></tbody></table>';
  }else{
    html+='<table><thead><tr><th style="width:55%">Repository</th><th style="width:12%">Stars</th><th style="width:15%">Language</th></tr></thead><tbody>';
    for(var i=0;i<repos.length;i++){
      var r=repos[i];
      var lang=r.language?'<span class="lg">'+r.language+'</span>':'';
      var topics=(r.topics||[]).map(function(t){return '<span class="tp">'+t+'</span>';}).join('');
      html+='<tr><td><a class="rn" href="'+r.url+'" target="_blank">'+r.name+'</a><div class="rd">'+(r.description||'')+'</div>'+(topics?'<div>'+topics+'</div>':'')+'</td>';
      html+='<td><span class="star">★</span> '+r.stars+'</td>';
      html+='<td>'+lang+'</td></tr>';
    }
    html+='</tbody></table>';
  }
  el.innerHTML=html;
  el.style.display='block';
}
</script>
</body>
</html>""".replace("{CSS}", CSS)


PAGE = INDEX_HTML
