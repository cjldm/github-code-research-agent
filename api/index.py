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

HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>GitHub Code Research Agent</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
.container{max-width:960px;margin:0 auto;padding:30px 20px}
h1{font-size:1.6rem;margin-bottom:4px;color:#58a6ff}
p.sub{color:#8b949e;margin-bottom:20px;font-size:0.9rem}
.search-row{display:flex;gap:8px;margin-bottom:16px}
.search-row input{flex:1;padding:10px 14px;background:#161b22;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:1rem;outline:none}
.search-row input:focus{border-color:#58a6ff}
.search-row button{padding:10px 24px;background:#238636;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:1rem;font-weight:600}
.search-row button:hover{background:#2ea043}
.search-row button:disabled{opacity:.5;cursor:not-allowed}
.chips{margin-bottom:20px}
.chip{display:inline-block;padding:4px 10px;background:#21262d;border-radius:4px;cursor:pointer;font-size:0.82rem;margin:2px 4px 2px 0;color:#58a6ff;border:1px solid #30363d}
.chip:hover{background:#30363d;border-color:#58a6ff}
#status{color:#8b949e;font-size:0.88rem;margin-bottom:14px;min-height:22px}
.result-section{display:none;margin-top:8px}
table{width:100%;border-collapse:collapse;font-size:0.85rem}
thead th{background:#161b22;padding:10px 12px;text-align:left;font-weight:600;color:#8b949e;border-bottom:1px solid #30363d;position:sticky;top:0}
tbody td{padding:10px 12px;border-bottom:1px solid #21262d;vertical-align:top}
tbody tr:hover{background:#161b22}
.repo-name{color:#58a6ff;font-weight:600;text-decoration:none}
.repo-name:hover{text-decoration:underline}
.repo-desc{color:#8b949e;font-size:0.8rem;margin-top:2px;line-height:1.4}
.star{color:#d29922;font-size:0.8rem}
.lang-tag{display:inline-block;padding:2px 6px;background:#1f2a36;border-radius:3px;font-size:0.75rem;color:#8b949e}
.topics{margin-top:3px}
.topic{display:inline-block;padding:1px 6px;background:#1f2a36;border-radius:10px;font-size:0.72rem;color:#58a6ff;margin:1px 2px}
.empty{text-align:center;padding:40px;color:#484f58}
.tech-card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:20px}
.tech-card h3{color:#58a6ff;font-size:1rem;margin-bottom:12px}
.tech-path{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.tech-step{background:#1c2333;border:1px solid #30363d;border-radius:6px;padding:8px 14px;text-align:center;flex:1;min-width:120px}
.tech-step .label{font-size:0.75rem;color:#8b949e;margin-bottom:4px}
.tech-step .value{font-size:0.85rem;color:#c9d1d9;font-weight:500}
.tech-desc{color:#8b949e;font-size:0.82rem;line-height:1.6;margin-top:8px}
.featured{display:flex;gap:12px;flex-wrap:wrap}
.featured-item{background:#1c2333;border:1px solid #30363d;border-radius:6px;padding:12px 16px;flex:1;min-width:200px}
.featured-item .fn{color:#58a6ff;font-size:0.85rem;font-weight:600}
.featured-item .fs{color:#d29922;font-size:0.8rem}
.featured-item .fd{color:#8b949e;font-size:0.78rem;margin-top:4px}
.footer{text-align:center;color:#484f58;font-size:0.78rem;margin-top:30px;padding-top:20px;border-top:1px solid #21262d}
</style>
</head>
<body>
<div class="container">
  <h1>GitHub Code Research Agent</h1>
  <p class="sub">输入需求 → 检索开源项目 → 输出推荐技术路径</p>
  <div class="search-row">
    <input id="query" placeholder="例如：建筑立面风格识别的 Python 项目" autofocus />
    <button id="btn">Search</button>
  </div>
  <div class="chips">
    <span class="chip" onclick="go('YOLOv8 object detection Python')">YOLOv8</span>
    <span class="chip" onclick="go('RAG document QA Python')">RAG QA</span>
    <span class="chip" onclick="go('architectural style recognition Python')">Architecture</span>
    <span class="chip" onclick="go('DWG floor plan parser Python')">DWG Parser</span>
  </div>
  <div id="status"></div>
  <div id="result" class="result-section"></div>
  <div class="footer">
    Web quick search. Full RAG analysis: <span style="color:#8b949e">python agent.py "your requirement"</span>
  </div>
</div>
<script>
function go(q){document.getElementById('query').value=q;search()}
async function search(){
  const inp=document.getElementById('query'),btn=document.getElementById('btn');
  const st=document.getElementById('status'),res=document.getElementById('result');
  const q=inp.value.trim();if(!q)return;
  btn.disabled=true;st.textContent='Searching...';res.style.display='none';
  try{
    const r=await fetch('/api/search?q='+encodeURIComponent(q));
    const d=await r.json();
    if(d.error){st.textContent='Error: '+d.error;return}
    render(d,q);st.textContent='Found '+d.candidates+' repos.';
  }catch(e){st.textContent='Failed: '+e.message}
  finally{btn.disabled=false}
}
function render(data,query){
  const repos=data.repos||[];const el=document.getElementById('result');
  const isArch=/建筑|立面|architecture|facade|architectural|style.*(recog|classif)/i.test(query);
  let tech='';
  if(isArch){
    tech='<div class="tech-card"><h3>Recommended Technical Path: Architectural Style Recognition</h3>'
      +'<div class="tech-path">'
      +'<div class="tech-step"><div class="label">Feature Extractor</div><div class="value">ResNet-50</div></div>'
      +'<div class="tech-step"><div class="label">Training</div><div class="value">Transfer Learning</div></div>'
      +'<div class="tech-step"><div class="label">Data</div><div class="value">Street View</div></div>'
      +'<div class="tech-step"><div class="label">Framework</div><div class="value">PyTorch + fastai</div></div>'
      +'</div>'
      +'<div class="tech-desc">Use transfer learning (ResNet-50 pre-trained on ImageNet). Fine-tune on facade images from Google Street View or ArchDataset. Data augmentation (rotation, crop, color jitter) handles lighting variance. Quantize to TensorRT/TFLite for edge deployment.</div>'
      +'<div style="margin-top:12px"><div class="featured">'
      +'<div class="featured-item"><div class="fn">dumitrux/architectural-style-recognition</div><div class="fs">★ 31</div><div class="fd">CNN + fastai, 25 styles, full pipeline</div></div>'
      +'<div class="featured-item"><div class="fn">AKASH2907/indian_landmark_recognition</div><div class="fs">★ 7</div><div class="fd">CNN + KNN ensemble, Python+Keras</div></div>'
      +'</div></div></div>';
  }
  let rows='';
  if(repos.length===0) rows='<tr><td colspan="3" class="empty">No results.</td></tr>';
  else repos.forEach(r=>{
    const l=r.language?'<span class="lang-tag">'+r.language+'</span>':'';
    const ts=(r.topics||[]).map(t=>'<span class="topic">'+t+'</span>').join('');
    rows+='<tr><td><a class="repo-name" href="'+r.url+'" target="_blank">'+r.name+'</a>'
      +'<div class="repo-desc">'+(r.description||'')+'</div>'+(ts?'<div class="topics">'+ts:'')+'</div></td>'
      +'<td style="white-space:nowrap"><span class="star">★</span> '+r.stars+'</td>'
      +'<td>'+l+'</td></tr>';
  });
  el.innerHTML=tech+'<table><thead><tr><th style="width:55%">Repository</th><th style="width:12%">Stars</th><th style="width:15%">Language</th></tr></thead><tbody>'+rows+'</tbody></table>';
  el.style.display='block';
}
</script>
</body>
</html>"""


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
        return {"query": q, "candidates": min(len(all_repos), 15), "repos": all_repos[:15]}
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)
