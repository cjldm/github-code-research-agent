import os, re, sys, traceback
from pathlib import Path
import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

app = FastAPI(title="GitHub Code Research Agent", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
.container{max-width:1000px;margin:0 auto;padding:30px 20px}
h1{font-size:1.6rem;margin:0 0 4px;color:#58a6ff}
.sub{color:#8b949e;margin-bottom:20px}
.srch{display:flex;gap:8px;margin-bottom:16px}
.srch input{flex:1;padding:10px 14px;background:#161b22;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:1rem;outline:none}
.srch input:focus{border-color:#58a6ff}
.srch button{padding:10px 24px;background:#238636;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:1rem;font-weight:600}
.srch button:disabled{opacity:.5}
.chip{display:inline-block;padding:4px 10px;background:#21262d;border:1px solid #30363d;border-radius:4px;cursor:pointer;font-size:.82rem;margin:2px 4px 2px 0;color:#58a6ff}
.chip:hover{background:#30363d;border-color:#58a6ff}
#st{color:#8b949e;margin-bottom:14px;min-height:22px}
#res{display:none;margin-top:8px}
.rec-card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:24px}
.rec-card h2{color:#58a6ff;font-size:1.1rem;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #21262d}
.rec-card h3{color:#c9d1d9;font-size:.9rem;margin:12px 0 8px}
.rec-card .best{background:#1c2333;border:1px solid #30363d;border-radius:6px;padding:14px;margin-bottom:12px}
.rec-card .best .bn{color:#58a6ff;font-size:1rem;font-weight:600}
.rec-card .best .bs{color:#d29922;font-size:.85rem}
.rec-card .best .bd{color:#8b949e;font-size:.82rem;margin-top:4px;line-height:1.5}
.rec-card .best .breason{color:#8b949e;font-size:.8rem;margin-top:8px;padding:8px;background:#0d1117;border-radius:4px;line-height:1.5}
.path-steps{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
.ps{background:#1c2333;border:1px solid #30363d;border-radius:6px;padding:8px 12px;text-align:center;flex:1;min-width:100px}
.ps .pl{font-size:.72rem;color:#8b949e;margin-bottom:2px}
.ps .pv{font-size:.85rem;color:#c9d1d9;font-weight:500}
table{width:100%;border-collapse:collapse;font-size:.82rem;border:1px solid #30363d;border-radius:6px;overflow:hidden}
th{background:#1c2333;padding:10px 12px;text-align:left;font-weight:600;color:#8b949e;border-bottom:1px solid #30363d;white-space:nowrap}
td{padding:10px 12px;border-bottom:1px solid #21262d;vertical-align:top}
tr:hover{background:#161b22}
.rn{color:#58a6ff;font-weight:600;text-decoration:none;font-size:.85rem}
.rn:hover{text-decoration:underline}
.rd{color:#8b949e;font-size:.78rem;margin-top:2px;line-height:1.4}
.star{color:#d29922;font-size:.82rem}
.lg{display:inline-block;padding:1px 5px;background:#1f2a36;border-radius:3px;font-size:.7rem;color:#8b949e}
.tp{display:inline-block;padding:1px 5px;background:#1f2a36;border-radius:8px;font-size:.68rem;color:#58a6ff;margin:1px}
.match-badge{display:inline-block;padding:2px 6px;border-radius:3px;font-size:.7rem;font-weight:600}
.match-high{background:#1a3a1a;color:#3fb950}
.match-med{background:#3a2e1a;color:#d29922}
.match-low{background:#3a1a1a;color:#f85149}
.ft{text-align:center;color:#484f58;font-size:.78rem;margin-top:30px;padding-top:20px;border-top:1px solid #21262d}
"""

BODY = """<div class="container">
<h1>GitHub Code Research Agent</h1>
<p class="sub">输入需求 - 检索开源项目 - 分析对比 - 推荐技术路径</p>
<div class="srch">
<input id="q" placeholder="例如：建筑立面风格识别的 Python 项目" autofocus>
<button id="btn">Search</button>
</div>
<div>
<span class="chip">建筑风格识别 Python</span>
<span class="chip">RAG QA Python</span>
<span class="chip">YOLOv8 detection</span>
<span class="chip">DWG floor plan</span>
</div>
<div id="st">Ready.</div>
<div id="res"></div>
<div class="ft">快速检索版 . 完整 RAG 代码分析: python agent.py</div>
</div>"""

JS = """
var domainDB = {
  'architecture': {kw:['建筑','立面','风格','architecture','facade','architectural','building style','style recognition'],
    steps:[{l:'Feature Extractor',v:'ResNet-50 / EfficientNet'},{l:'Training',v:'Transfer Learning'},
      {l:'Framework',v:'PyTorch / fastai'},{l:'Data',v:'Street View / ArchDataset'}],
    desc:'Use pre-trained ResNet-50 (ImageNet) with transfer learning. Fine-tune FC layer for N-class style classification. Data augmentation for lighting/angle variance. Quantize to TensorRT/TFLite for edge deployment.'},
  'rag': {kw:['rag','document qa','retrieval','qa system','question answering','knowledge base'],
    steps:[{l:'Embedding',v:'text-embedding-3'},{l:'Vector Store',v:'FAISS / Chroma'},
      {l:'Retriever',v:'Hybrid (BM25+Sem)'},{l:'Generator',v:'GPT-4 / DeepSeek'}],
    desc:'Split docs into chunks (500-1000 tokens, overlap). Embed and store in FAISS. Hybrid retrieval: semantic + BM25. Pass top-k chunks as context to LLM.'},
  'yolo': {kw:['yolo','object detection','目标检测','real-time detection'],
    steps:[{l:'Backbone',v:'CSPDarknet'},{l:'Neck',v:'PAN-FPN'},{l:'Head',v:'Decoupled Head'},
      {l:'Loss',v:'CIoU + DFL + BCE'}],
    desc:'CSPDarknet backbone, PAN-FPN multi-scale fusion, Decoupled Head for cls/reg. CIoU + DFL + BCE joint optimization.'},
  'dwg': {kw:['dwg','dxf','cad','floor plan','平面图','建筑图纸'],
    steps:[{l:'Parser',v:'ezdxf / LibreDWG'},{l:'Vectorization',v:'R2V / Hough'},{l:'Recognition',v:'Graph NN'},
      {l:'Output',v:'IFC / SVG / JSON'}],
    desc:'Parse DWG/DXF with ezdxf, vectorize via Hough transform or DL, recognize building elements (walls, doors, windows) with GNN, output structured IFC or JSON.'}
};

function detectDomain(q) {
  var ql = q.toLowerCase();
  for (var key in domainDB) {
    var db = domainDB[key];
    for (var i = 0; i < db.kw.length; i++) {
      if (ql.indexOf(db.kw[i]) !== -1) return key;
    }
  }
  return null;
}

function calcMatch(repo, query) {
  var score = 0;
  var ql = query.toLowerCase();
  var text = (repo.name + ' ' + (repo.description||'') + ' ' + (repo.topics||[]).join(' ')).toLowerCase();
  var words = ql.split(/[\\s,\\-_]+/);
  for (var i = 0; i < words.length; i++) {
    if (words[i].length < 3) continue;
    if (text.indexOf(words[i]) !== -1) score += 10;
  }
  score += Math.min(repo.stars / 100, 30);
  if (repo.language && repo.language.toLowerCase() === 'python') score += 15;
  if (repo.topics && repo.topics.length > 0) score += 5;
  return Math.min(score, 100);
}

function sortByMatch(repos, query) {
  for (var i = 0; i < repos.length; i++) repos[i]._match = calcMatch(repos[i], query);
  repos.sort(function(a,b){return b._match - a._match;});
  return repos;
}

document.getElementById('btn').onclick = function() {
  var q = document.getElementById('q').value.trim();
  if (!q) return;
  var btn = document.getElementById('btn'), st = document.getElementById('st'), res = document.getElementById('res');
  btn.disabled = true;
  st.textContent = 'Searching and analyzing...';
  res.style.display = 'none';
  var xhr = new XMLHttpRequest();
  xhr.open('GET', '/api/search?q=' + encodeURIComponent(q));
  xhr.onload = function() {
    btn.disabled = false;
    if (xhr.status !== 200) { st.textContent = 'Error: ' + xhr.status; return; }
    var d = JSON.parse(xhr.responseText);
    if (d.error) { st.textContent = 'Error: ' + d.error; return; }
    renderResults(d, q);
    st.textContent = 'Found ' + d.candidates + ' repos.';
  };
  xhr.onerror = function() { btn.disabled = false; st.textContent = 'Network error'; };
  xhr.send();
};

var chips = document.querySelectorAll('.chip');
for (var i = 0; i < chips.length; i++) {
  chips[i].onclick = function() {
    document.getElementById('q').value = this.textContent;
    document.getElementById('btn').click();
  };
}

function renderResults(d, q) {
  var repos = d.repos || [];
  var el = document.getElementById('res');
  repos = sortByMatch(repos, q);
  var domain = detectDomain(q);
  var html = '';

  html += '<div class="rec-card"><h2>Project Analysis and Recommendation</h2>';
  if (repos.length > 0) {
    var best = repos[0];
    var mc = best._match >= 60 ? 'match-high' : (best._match >= 40 ? 'match-med' : 'match-low');
    var ml = best._match >= 60 ? 'High' : (best._match >= 40 ? 'Med' : 'Low');
    html += '<h3>Best Match</h3><div class="best">';
    html += '<div><span class="bn">' + best.name + '</span> <span class="bs">* ' + best.stars + '</span> <span class="' + mc + ' match-badge">' + ml + ' (' + best._match + '%)</span></div>';
    html += '<div class="bd">' + (best.description||'') + '</div>';
    if (best.topics) for (var ti=0;ti<best.topics.length;ti++) html += '<span class="tp">' + best.topics[ti] + '</span>';
    var reason = [];
    if (best._match>=60) reason.push('High relevance ('+best._match+'%)');
    if (best.stars>50) reason.push(best.stars+' stars, active community');
    else if (best.stars>10) reason.push(best.stars+' stars');
    html += '<div class="breason">Why: ' + reason.join('. ') + '.</div></div>';
  }

  if (domain && domainDB[domain]) {
    var db = domainDB[domain];
    html += '<h3>Recommended Tech Path: ' + domain + '</h3><div class="path-steps">';
    for (var si=0;si<db.steps.length;si++) html += '<div class="ps"><div class="pl">' + db.steps[si].l + '</div><div class="pv">' + db.steps[si].v + '</div></div>';
    html += '</div><div style="color:#8b949e;font-size:.82rem;line-height:1.6">' + db.desc + '</div>';
  } else {
    html += '<h3>General Approach</h3><div class="path-steps">';
    html += '<div class="ps"><div class="pl">Search</div><div class="pv">GitHub Scan</div></div><div class="ps"><div class="pl">Evaluate</div><div class="pv">Code Review</div></div>';
    html += '<div class="ps"><div class="pl">Compare</div><div class="pv">Stars+Topics</div></div><div class="ps"><div class="pl">Select</div><div class="pv">Best Fit</div></div></div>';
  }

  html += '<h3>Implementation Steps</h3><div class="best" style="margin-top:8px">';
  var steps = domain === 'architecture' ? ['Collect facade images (Street View / ArchDataset)','Preprocess: resize 224x224, augment (rotate, crop, jitter)','Load pre-trained ResNet-50, replace FC layer for N-class','Train with transfer learning (freeze backbone, fine-tune)','Evaluate: accuracy, confusion matrix','Deploy: quantize to TensorRT/TFLite']
    : (domain==='rag'?['Split docs (500-1000 tokens, overlap)','Embed and store in FAISS','Hybrid retrieval (semantic+BM25)','Pass top-k as context to LLM','Evaluate: faithfulness, precision']
    : ['Clone top repo: ' + (repos[0]?repos[0].name:'selected repo'),'Review core algorithm and data pipeline','Adapt to your domain','Test with your data','Iterate']);
  for (var si2=0;si2<steps.length;si2++) html += '<div style="margin:4px 0;font-size:.82rem;color:#8b949e"><span style="color:#58a6ff;margin-right:4px">' + (si2+1) + '.</span>' + steps[si2] + '</div>';
  html += '</div></div>';

  html += '<table><thead><tr><th style="width:36%">Repository</th><th style="width:8%">Match</th><th style="width:7%">Stars</th><th style="width:7%">Lang</th><th style="width:10%">Method</th><th style="width:32%">Conclusion</th></tr></thead><tbody>';
  if (repos.length===0) html += '<tr><td colspan="6" style="text-align:center;padding:40px;color:#484f58">No results.</td></tr>';
  else {
    for (var ri=0;ri<repos.length;ri++) {
      var r=repos[ri];
      var mc2=r._match>=60?'match-high':(r._match>=40?'match-med':'match-low');
      var ml2=r._match>=60?'High':(r._match>=40?'Med':'Low');
      var topics='';if(r.topics) for(var ti=0;ti<Math.min(r.topics.length,3);ti++) topics+='<span class="tp">'+r.topics[ti]+'</span>';
      var meth='DL'; var txt=(r.name+' '+(r.description||'')+' '+(r.topics||[]).join(' ')).toLowerCase();
      if(txt.indexOf('cnn')!==-1||txt.indexOf('resnet')!==-1) meth='CNN/ResNet';
      else if(txt.indexOf('transformer')!==-1||txt.indexOf('attention')!==-1) meth='Transformer';
      else if(txt.indexOf('yolo')!==-1) meth='YOLO';
      else if(txt.indexOf('rag')!==-1||txt.indexOf('retrieval')!==-1) meth='RAG';
      else if(txt.indexOf('clip')!==-1) meth='CLIP';
      else if(txt.indexOf('svm')!==-1) meth='SVM';
      else if(txt.indexOf('fastai')!==-1) meth='fastai';
      var conc=r._match>=60?'Strong match. Reusable code.':(r._match>=40?'Partially relevant. Needs adaptation.':'Background reference.');
      html += '<tr><td><a class="rn" href="'+r.url+'" target="_blank">'+r.name+'</a>'+topics+'</td>';
      html += '<td><span class="'+mc2+' match-badge">'+r._match+'</span></td><td><span class="star">*</span> '+r.stars+'</td>';
      html += '<td>'+(r.language?'<span class="lg">'+r.language+'</span>':'-')+'</td>';
      html += '<td style="font-size:.78rem;color:#8b949e">'+meth+'</td><td style="font-size:.78rem;color:#8b949e">'+conc+'</td></tr>';
    }
  }
  html += '</tbody></table>';
  el.innerHTML = html;
  el.style.display = 'block';
}
"""

HTML_PAGE = "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"UTF-8\">\n<meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\">\n<title>GitHub Code Research Agent</title>\n<style>" + CSS + "</style>\n</head>\n<body>\n" + BODY + "\n<script>" + JS + "</script>\n</body>\n</html>"


def gh_headers():
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PAT")
    h = {"Accept": "application/vnd.github+json", "User-Agent": "gh-code-agent"}
    if token:
        h["Authorization"] = "Bearer " + token
    return h


def search_gh(query, limit=10):
    try:
        resp = requests.get("https://api.github.com/search/repositories",
            headers=gh_headers(),
            params={"q": query, "sort": "stars", "order": "desc", "per_page": limit},
            timeout=30)
        if resp.status_code in (403, 429):
            return []
        resp.raise_for_status()
        return resp.json().get("items", [])
    except:
        return []


def expand_queries(text):
    t = text.strip()
    qs = [t + " in:name,description,readme"]
    arch = ["建筑", "立面", "风格", "architecture", "facade", "architectural"]
    if any(a in t for a in arch):
        qs += ['"architectural style recognition"', '"architecture style classification"',
               '"building facade classification"', "architectural style recognition python"]
    if "python" not in t.lower():
        qs.append(t + " language:Python")
        qs.append(t + " Python")
    seen = set()
    return [q for q in qs if not (q in seen or seen.add(q))]


def is_relevant(item, query):
    txt = (item.get("full_name","") + " " + (item.get("description") or "")).lower()
    if any(k in txt for k in ["independent", "blog", "买房", "润学", "awesome"]):
        return False
    arch = ["建筑", "立面", "architecture", "facade", "architectural", "building", "style"]
    if any(a in query.lower() for a in arch):
        return any(a in txt for a in arch) and any(t in txt for t in ("classification", "recognition", "识别"))
    return True


def fmt(item):
    return {"name": item.get("full_name",""), "url": item.get("html_url",""),
            "description": (item.get("description") or "")[:200],
            "language": item.get("language") or "", "stars": item.get("stargazers_count", 0),
            "topics": item.get("topics", [])[:5]}


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML_PAGE


@app.get("/api/search")
async def search(q: str = Query(...)):
    try:
        seen, all_repos = set(), []
        for query in expand_queries(q)[:8]:
            for item in search_gh(query, 8):
                name = item.get("full_name", "")
                if name and name not in seen:
                    seen.add(name)
                    if is_relevant(item, q):
                        all_repos.append(fmt(item))
        all_repos.sort(key=lambda x: x.get("stars", 0), reverse=True)
        return {"query": q, "candidates": min(len(all_repos), 15), "repos": all_repos[:15]}
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)
