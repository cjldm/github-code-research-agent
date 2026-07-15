"""FastAPI web interface for the GitHub Code Research Agent."""
from __future__ import annotations

import json
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub Code Research Agent</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
        .container{max-width:800px;margin:0 auto;padding:40px 20px}
        h1{font-size:1.8rem;margin-bottom:8px;color:#58a6ff}
        p.sub{color:#8b949e;margin-bottom:24px}
        .input-group{display:flex;gap:8px;margin-bottom:16px}
        input{flex:1;padding:12px 16px;background:#161b22;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:1rem}
        button{padding:12px 24px;background:#238636;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:1rem;font-weight:600}
        button:hover{background:#2ea043}
        button:disabled{opacity:0.6;cursor:not-allowed}
        #status{color:#8b949e;font-size:0.9rem;margin-bottom:16px;min-height:20px}
        #result{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:16px;white-space:pre-wrap;font-family:monospace;font-size:0.85rem;display:none;max-height:70vh;overflow-y:auto}
        .example{display:inline-block;padding:4px 8px;background:#21262d;border-radius:4px;cursor:pointer;font-size:0.85rem;margin:2px;color:#58a6ff}
        .example:hover{background:#30363d}
    </style>
</head>
<body>
<div class="container">
    <h1>GitHub Code Research Agent</h1>
    <p class="sub">输入需求，自动检索 GitHub 项目、分析代码、输出推荐方案</p>
    <div class="input-group">
        <input id="query" placeholder="例如：建筑立面风格识别的 Python 项目" />
        <button id="searchBtn">Search</button>
    </div>
    <div>
        <span class="example" onclick="search('YOLOv8 object detection Python')">YOLOv8</span>
        <span class="example" onclick="search('RAG document QA Python')">RAG QA</span>
        <span class="example" onclick="search('建筑立面风格识别 Python')">Architecture</span>
        <span class="example" onclick="search('DWG floor plan parser Python')">DWG</span>
    </div>
    <div id="status"></div>
    <div id="result"></div>
</div>
<script>
async function search(q) {
    const inp=document.getElementById('query'),btn=document.getElementById('searchBtn');
    const st=document.getElementById('status'),res=document.getElementById('result');
    const query=q||inp.value.trim();if(!query)return;
    inp.value=query;btn.disabled=true;st.textContent='Searching...';res.style.display='none';
    try{
        const r=await fetch('/api/search?q='+encodeURIComponent(query));
        const d=await r.json();
        res.style.display='block';res.textContent=JSON.stringify(d,null,2);
        st.textContent=d.error?'Error: '+d.error:'Found '+(d.candidates||0)+' repos.';
    }catch(e){res.style.display='block';res.textContent='Error: '+e.message;st.textContent='Failed.'}
    finally{btn.disabled=false}
}
document.getElementById('searchBtn').addEventListener('click',()=>search());
document.getElementById('query').addEventListener('keydown',e=>{if(e.key==='Enter')search()});
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML_PAGE


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
            return [{"error": "Rate limited", "query": query}]
        resp.raise_for_status()
        return resp.json().get("items", [])
    except Exception as exc:
        return [{"error": str(exc), "query": query}]


def _expand_queries(text: str) -> list[str]:
    t = text.strip()
    queries = []
    queries.append(f"{t} in:name,description,readme")
    has_cjk = bool(re.search(r"[一-鿿]", t))
    arch_terms = ["建筑", "立面", "风格", "architecture", "facade", "architectural"]
    if any(a in t for a in arch_terms):
        queries.extend([
            '"architectural style recognition"',
            '"architecture style classification"',
            '"building facade classification"',
            'architectural style recognition python',
        ])
        queries.append(f"{t} language:Python")
    if "python" not in t.lower() and not has_cjk:
        queries.append(f"{t} language:Python")
        queries.append(f"{t} Python")
    seen = set()
    return [q for q in queries if not (q in seen or seen.add(q))]


def _is_relevant(item: dict, original_query: str) -> bool:
    name = (item.get("full_name") or "").lower()
    desc = (item.get("description") or "").lower()
    text = f"{name} {desc}"
    exclude = ["独立开发者", "independent-developer", "独立博客", "博客列表",
               "买房", "润学", "run-philosophy", "awesome-list", "awesome list"]
    if any(k in text for k in exclude):
        return False
    arch_related = ["建筑", "立面", "风格识别", "architecture", "facade",
                    "architectural", "building", "style classification"]
    if any(a in original_query.lower() for a in arch_related):
        domain = any(a in text for a in arch_related)
        task = any(t in text for t in ("classification", "recognition", "识别", "分类", "detection"))
        return domain or task
    return True


def _format_repo(item: dict) -> dict:
    return {
        "name": item.get("full_name", ""),
        "url": item.get("html_url", ""),
        "description": (item.get("description") or "")[:200],
        "language": item.get("language") or "",
        "stars": item.get("stargazers_count", 0),
        "topics": item.get("topics", [])[:5],
        "updated": (item.get("updated_at") or "")[:10],
    }


@app.get("/api/search")
async def search(q: str = Query(..., description="Natural language requirement")):
    try:
        queries = _expand_queries(q)
        seen_names = set()
        all_repos = []
        for query in queries[:8]:
            items = _search_gh(query, limit=8)
            if isinstance(items, list) and items and "error" not in items[0]:
                for item in items:
                    name = item.get("full_name", "")
                    if name and name not in seen_names:
                        seen_names.add(name)
                        if _is_relevant(item, q):
                            all_repos.append(_format_repo(item))
        all_repos.sort(key=lambda x: x.get("stars", 0), reverse=True)
        return {
            "query": q,
            "candidates": min(len(all_repos), 15),
            "note": "Web quick search. Run locally for full RAG code analysis.",
            "repos": all_repos[:15],
        }
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)
