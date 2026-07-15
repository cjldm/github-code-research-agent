"""FastAPI web interface for the GitHub Code Research Agent."""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

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
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #0d1117; color: #c9d1d9; min-height: 100vh; }
        .container { max-width: 800px; margin: 0 auto; padding: 40px 20px; }
        h1 { font-size: 1.8rem; margin-bottom: 8px; color: #58a6ff; }
        p.sub { color: #8b949e; margin-bottom: 24px; }
        .input-group { display: flex; gap: 8px; margin-bottom: 16px; }
        input { flex: 1; padding: 12px 16px; background: #161b22; border: 1px solid #30363d;
                border-radius: 6px; color: #c9d1d9; font-size: 1rem; }
        button { padding: 12px 24px; background: #238636; color: #fff; border: none;
                 border-radius: 6px; cursor: pointer; font-size: 1rem; font-weight: 600; }
        button:hover { background: #2ea043; }
        button:disabled { opacity: 0.6; cursor: not-allowed; }
        #status { color: #8b949e; font-size: 0.9rem; margin-bottom: 16px; min-height: 20px; }
        #result { background: #161b22; border: 1px solid #30363d; border-radius: 6px;
                  padding: 16px; white-space: pre-wrap; font-family: monospace;
                  font-size: 0.85rem; display: none; max-height: 70vh; overflow-y: auto; }
        .example { display: inline-block; padding: 4px 8px; background: #21262d;
                   border-radius: 4px; cursor: pointer; font-size: 0.85rem;
                   margin: 2px; color: #58a6ff; }
        .example:hover { background: #30363d; }
    </style>
</head>
<body>
    <div class="container">
        <h1>GitHub Code Research Agent</h1>
        <p class="sub">Search GitHub repos and analyze code via RAG</p>
        <div class="input-group">
            <input id="query" placeholder="e.g. YOLOv8 object detection Python" />
            <button id="searchBtn">Search</button>
        </div>
        <div>
            <span class="example" onclick="search('YOLOv8 object detection Python')">YOLOv8</span>
            <span class="example" onclick="search('RAG document QA Python')">RAG QA</span>
            <span class="example" onclick="search('architectural style classification Python')">Architecture</span>
            <span class="example" onclick="search('DWG floor plan parser Python')">DWG Parser</span>
        </div>
        <div id="status"></div>
        <div id="result"></div>
    </div>
    <script>
        async function search(q) {
            const input = document.getElementById('query');
            const btn = document.getElementById('searchBtn');
            const status = document.getElementById('status');
            const result = document.getElementById('result');
            const query = q || input.value.trim();
            if (!query) return;
            input.value = query;
            btn.disabled = true;
            status.textContent = 'Searching GitHub...';
            result.style.display = 'none';
            try {
                const resp = await fetch('/api/search?q=' + encodeURIComponent(query));
                const data = await resp.json();
                result.style.display = 'block';
                result.textContent = JSON.stringify(data, null, 2);
                status.textContent = data.error ? 'Error: ' + data.error : 'Found ' + (data.candidates || 0) + ' repos.';
            } catch (e) {
                result.style.display = 'block';
                result.textContent = 'Error: ' + e.message;
                status.textContent = 'Request failed.';
            } finally {
                btn.disabled = false;
            }
        }
        document.getElementById('searchBtn').addEventListener('click', () => search());
        document.getElementById('query').addEventListener('keydown', e => { if (e.key === 'Enter') search(); });
    </script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML_PAGE


@app.get("/api/search")
async def search(q: str = Query(..., description="Natural language search query")):
    """Search GitHub repos matching the requirement."""
    try:
        from core.models import QueryPlan
        plan = QueryPlan(
            search_queries=[f"{q} in:name,description,readme"],
            must_have=[q], exclude_if=[],
        )
        from core.github import search_github_api
        seen, all_c = set(), []
        for query in plan.search_queries:
            for c in search_github_api(query, 5):
                if c.full_name and c.full_name not in seen:
                    seen.add(c.full_name)
                    all_c.append(c)
        all_c.sort(key=lambda x: x.stars, reverse=True)
        return {
            "query": q,
            "candidates": len(all_c),
            "repos": [
                {"name": c.full_name, "url": c.html_url,
                 "description": c.description, "language": c.language, "stars": c.stars}
                for c in all_c
            ],
        }
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)
