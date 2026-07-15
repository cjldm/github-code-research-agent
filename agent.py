import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""GitHub Code Research Agent — search, analyze, recommend."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import warnings
from pathlib import Path

from dotenv import load_dotenv

warnings.filterwarnings("ignore", message="`langchain-community` is being sunset.*", category=DeprecationWarning)

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
WORKSPACE = ROOT / "workspace"
REPOS_DIR = WORKSPACE / "repos"
REPORTS_DIR = WORKSPACE / "reports"
INDEX_DIR = Path(os.getenv("AGENT_INDEX_DIR", Path.home() / ".github_code_agent_cache" / "indexes"))


def _ensure_dirs():
    for p in (WORKSPACE, REPOS_DIR, REPORTS_DIR, INDEX_DIR):
        p.mkdir(parents=True, exist_ok=True)


def _validate_config():
    if os.getenv("CHAT_MODEL_PROVIDER", "deepseek").lower() == "deepseek" and not os.getenv("DEEPSEEK_API_KEY"):
        raise SystemExit(f"Missing DEEPSEEK_API_KEY. See {ROOT / '.env.example'}")


def _check_deps():
    missing = []
    for mod, pkg in [("langchain_deepseek", "langchain-deepseek"), ("langchain_community", "langchain-community"),
                     ("langchain", "langchain")]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        raise SystemExit(f"pip install {' '.join(sorted(set(missing)))}")


def _cjk(text):
    return any("一" <= c <= "鿿" for c in text)


def _arch_style(text):
    l = text.lower()
    return any(t in l for t in ("建筑", "立面", "architecture", "architectural", "facade")) and \
           any(t in l for t in ("风格", "style")) and \
           any(t in l for t in ("识别", "分类", "recognition", "classification"))


def _parse_spec(requirement: str):
    from core.models import RequirementSpec
    r = requirement.strip()
    if r.startswith("{"):
        try:
            d = json.loads(r)
            if isinstance(d, dict):
                d.setdefault("raw_requirement", d.get("query", r))
                return RequirementSpec(**d)
        except Exception:
            pass
    if _arch_style(r):
        return RequirementSpec(raw_requirement=r, domain="architecture",
            target_object=["architectural style", "building facade"],
            task=["recognition", "classification"], modality=["image"],
            strict_terms=["architectural style", "style recognition"],
            related_terms=["facade segmentation", "architectural heritage classification"],
            exclude_terms=["generic course", "software architecture", "awesome list", "LLM/agent"])
    return RequirementSpec(raw_requirement=r, strict_terms=[r], exclude_terms=["no src"])


def _quote(t):
    t = t.strip()
    return f'"{t}"' if " " in t and not (t.startswith('"') and t.endswith('"')) else t


async def _make_spec(requirement: str):
    from core.models import RequirementSpec
    from core.rag import structured_ainvoke
    p = _parse_spec(requirement)
    if requirement.strip().startswith("{") or _arch_style(requirement):
        return p
    try:
        s = await structured_ainvoke(RequirementSpec, "SEARCH_MODEL",
            "Decompose user requirement into structured fields. Default lang: Python.", f"Req: {requirement}")
        s.raw_requirement = s.raw_requirement or requirement
        s.language = s.language or ["Python"]
        return s
    except Exception:
        return p


def _mk_plan(spec):
    from core.models import QueryPlan
    lang = (spec.language or ["Python"])[0]
    objs = spec.target_object or spec.strict_terms or [spec.raw_requirement]
    tasks = spec.task or ["implementation"]
    qs = []
    for t in (spec.strict_terms or [f"{objs[0]} {tasks[0]}"])[:8]:
        qs += [f"{_quote(t)} {lang}", f"{t} {lang} in:readme,description"]
    for o in objs[:5]:
        for t in tasks[:4]:
            qs += [f"{_quote(o)} {t} {lang}", f"{o} {t} {lang} in:readme,description"]
    if spec.allow_related:
        for r in spec.related_terms[:8]:
            qs += [f"{_quote(r)} {lang}", f"{r} {lang} in:readme,description"]
    return QueryPlan(search_queries=list(dict.fromkeys(qs))[:30],
        must_have=[f"domain:{spec.domain}", f"target:{objs[:3]}"],
        exclude_if=spec.exclude_terms or ["awesome list only"])


def _arch_plan(spec):
    from core.models import QueryPlan
    q = ['"architectural style recognition" python', '"architecture style classification" python',
         '"building facade style classification" python', '"facade style classification" python',
         'architectural style recognition python in:readme', '"facade segmentation" python']
    return QueryPlan(search_queries=q, must_have=["visual recognition of architecture"],
        exclude_if=["software architecture", "generic course", "awesome list"])


async def _query_plan(requirement: str):
    s = await _make_spec(requirement)
    return _arch_plan(s) if _arch_style(s.raw_requirement) else _mk_plan(s)


def _arch_match(text):
    l = text.lower()
    if any(t in l for t in ("software architecture", "awesome", "course", "lecture", "llm")):
        return False
    return any(t in l for t in ("architectural style", "building facade", "facade", "建筑", "立面"))


async def _search(plan, max_results: int):
    from core.github import search_github_api, search_github_mcp
    seen, all_c = set(), []
    per_q = max(3, min(20, max_results))
    backend = os.getenv("GITHUB_SEARCH_BACKEND", "api").lower()
    for q in plan.search_queries:
        print(f"[search] {q}")
        cs = None
        if backend in {"mcp", "auto"}:
            cs = await search_github_mcp(q, per_q)
        if cs is None:
            cs = search_github_api(q, per_q)
        for c in cs:
            if c.full_name and c.full_name not in seen:
                txt = f"{c.full_name} {c.description} {c.language}".lower()
                if _arch_style(" ".join(plan.search_queries)) and not _arch_match(txt):
                    seen.add(c.full_name)
                    continue
                seen.add(c.full_name)
                all_c.append(c)
        if len(all_c) >= max_results:
            break
    return sorted(all_c, key=lambda x: x.stars, reverse=True)[:max_results]


async def run(requirement: str, max_results: int, keep: int, refresh: bool):
    _ensure_dirs()
    _check_deps()
    plan = await _query_plan(requirement)
    print("[plan]", json.dumps(plan.model_dump(), ensure_ascii=False, indent=2))
    candidates = await _search(plan, max_results)
    if not candidates:
        raise RuntimeError("No candidates. Try different keywords or configure GITHUB_TOKEN.")

    from core.github import snapshot_repo
    from core.rag import screen_snapshot, analyze_project, synthesize
    from core.reporter import write_reports
    from core.github import SKIP_DIRS as _SKIP

    kept, rejected = [], []
    for c in candidates:
        print(f"[repo] downloading {c.full_name}")
        snap = snapshot_repo(c, REPOS_DIR, refresh)
        if snap is None:
            continue
        d = await screen_snapshot(requirement, plan, snap)
        print(f"[screen] {c.full_name}: keep={d.keep} score={d.relevance_score}")
        if d.keep:
            kept.append(snap)
        else:
            rejected.append((c.full_name, d.reason))
        if len(kept) >= keep:
            break
    if not kept:
        raise RuntimeError(f"All excluded.\n" + "\n".join(f"- {n}: {r}" for n, r in rejected[:8]))

    analyses = [await analyze_project(requirement, s, INDEX_DIR, _SKIP) for s in kept]
    final = await synthesize(requirement, analyses)
    return write_reports(requirement, final, analyses, REPORTS_DIR)


def main():
    ap = argparse.ArgumentParser(description="GitHub Code Research Agent")
    ap.add_argument("requirement", nargs="?", help="Natural language search query")
    ap.add_argument("--spec-file", help="Path to structured requirement JSON")
    ap.add_argument("--max-results", type=int, default=24)
    ap.add_argument("--keep", type=int, default=8)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    if args.spec_file:
        args.requirement = Path(args.spec_file).read_text(encoding="utf-8")
    if not args.requirement:
        args.requirement = input("Enter search requirement: ").strip()
    if not args.requirement:
        raise SystemExit("No input.")
    _validate_config()
    try:
        md, jp = asyncio.run(run(args.requirement, args.max_results, args.keep, args.refresh))
    except KeyboardInterrupt:
        print("Cancelled.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n[error] {exc}")
        if os.getenv("DEBUG"):
            raise
        raise SystemExit(1)
    print(f"\nDone.\nMD: {md}\nJSON: {jp}")


if __name__ == "__main__":
    main()
