"""GitHub search, repository download, and snapshot utilities."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import requests

from .models import RepoCandidate, RepoSnapshot

SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env",
             "node_modules", "dist", "build", ".next", ".turbo", ".cache",
             "target", "vendor", "data", "datasets", "checkpoints", "weights"}

TEXT_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs",
                   ".cpp", ".c", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
                   ".kt", ".scala", ".m", ".mm", ".r", ".jl", ".sh", ".ps1",
                   ".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json",
                   ".ini", ".cfg", ".xml", ".html", ".css", ".sql"}

IMPORTANT_NAMES = {"readme", "requirements", "pyproject", "setup", "package",
                   "pom", "build", "dockerfile", "makefile", "environment",
                   "config", "main", "app", "server", "cli", "train", "infer",
                   "pipeline", "agent"}


def github_headers() -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PAT")
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
         "User-Agent": "github-code-research-agent"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def parse_repo_items(items: list[dict]) -> list[RepoCandidate]:
    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        fn = item.get("full_name") or item.get("nameWithOwner") or item.get("name") or ""
        hu = item.get("html_url") or item.get("url") or item.get("web_url") or ""
        if not hu and fn:
            hu = f"https://github.com/{fn}"
        candidates.append(RepoCandidate(
            full_name=fn, html_url=hu,
            clone_url=item.get("clone_url") or item.get("ssh_url") or f"{hu}.git",
            description=item.get("description") or "",
            language=item.get("language") or "",
            stars=int(item.get("stargazers_count") or item.get("stars") or 0),
            forks=int(item.get("forks_count") or item.get("forks") or 0),
            updated_at=item.get("updated_at") or item.get("updatedAt") or "",
            default_branch=item.get("default_branch") or "main",
        ))
    return candidates


def extract_repo_items_from_mcp_result(result):
    def unwrap(v):
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                return []
        if isinstance(v, dict):
            for k in ("items", "repositories", "repos", "results", "data"):
                n = v.get(k)
                if isinstance(n, list):
                    return unwrap(n)
                if isinstance(n, dict):
                    return unwrap(n)
            if v.get("full_name") or v.get("html_url"):
                return [v]
            return []
        if isinstance(v, list):
            repo_like = [i for i in v if isinstance(i, dict) and (i.get("full_name") or i.get("html_url"))]
            if repo_like:
                return repo_like
        return []
    return unwrap(result)


def search_github_api(query: str, limit: int) -> list[RepoCandidate]:
    try:
        resp = requests.get(
            "https://api.github.com/search/repositories",
            headers=github_headers(),
            params={"q": query, "sort": "stars", "order": "desc", "per_page": min(limit, 100)},
            timeout=40,
        )
        if resp.status_code in {403, 429}:
            print(f"[warn] rate limited: {query}")
            return []
        resp.raise_for_status()
        return parse_repo_items(resp.json().get("items", []))
    except Exception as exc:
        print(f"[warn] search failed: {query} ({exc})")
        return []


async def search_github_mcp(query: str, limit: int):
    if os.getenv("GITHUB_MCP_ENABLED", "0") != "1":
        return None
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        return None
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PAT") or ""
    client = MultiServerMCPClient({"github": {
        "command": os.getenv("GITHUB_MCP_COMMAND", "docker"),
        "args": json.loads(os.getenv("GITHUB_MCP_ARGS", "[]")),
        "transport": "stdio",
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": token,
                "GITHUB_TOOLSETS": os.getenv("GITHUB_TOOLSETS", "repos"),
                "GITHUB_READ_ONLY": os.getenv("GITHUB_READ_ONLY", "1")},
    }})
    try:
        tools = await client.get_tools()
        st = next((t for t in tools if "search" in t.name and "repo" in t.name), None)
        if not st:
            return None
        result = await st.ainvoke({"query": query, "perPage": min(limit, 100)})
        items = extract_repo_items_from_mcp_result(result)
        return parse_repo_items(items)[:limit]
    except Exception as exc:
        print(f"[warn] MCP failed: {exc}")
        return None


def safe_dir_name(full_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", full_name)


def _read_text(path, max_chars: int = 30_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""


def _strip_vcs(p):
    for n in (".git", ".hg", ".svn"):
        d = p / n
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


def snapshot_repo(candidate: RepoCandidate, repos_dir, refresh: bool = False) -> RepoSnapshot | None:
    repos_dir = Path(repos_dir)
    lp = repos_dir / safe_dir_name(candidate.full_name)
    if lp.exists() and refresh:
        shutil.rmtree(lp)
    if not lp.exists():
        dl = _download_zip(candidate, repos_dir, lp)
        if dl is None:
            try:
                subprocess.run(["git", "clone", "--depth", "1", candidate.clone_url, str(lp)],
                               check=True, capture_output=True, timeout=240)
                _strip_vcs(lp)
            except Exception as exc:
                print(f"[warn] clone failed: {exc}")
                dl = _download_zip(candidate, repos_dir, lp)
                if dl is None:
                    return None
    _strip_vcs(lp)
    return RepoSnapshot(
        candidate=candidate, local_path=lp,
        tree=_build_tree(lp), readme=_find_readme(lp),
        key_files=_collect_key_files(lp),
    )


def _download_zip(candidate, repos_dir, local_path):
    repos_dir = Path(repos_dir)
    for branch in dict.fromkeys([candidate.default_branch, "main", "master"]):
        if not branch:
            continue
        url = f"https://codeload.github.com/{candidate.full_name}/zip/refs/heads/{branch}"
        try:
            resp = requests.get(url, headers=github_headers(), timeout=120)
            if resp.status_code != 200:
                continue
            zpath = repos_dir / f"{safe_dir_name(candidate.full_name)}.zip"
            zpath.write_bytes(resp.content)
            tdir = repos_dir / f"{safe_dir_name(candidate.full_name)}__tmp"
            if tdir.exists():
                shutil.rmtree(tdir, ignore_errors=True)
            tdir.mkdir(parents=True, exist_ok=True)
            import zipfile as zf
            with zf.ZipFile(zpath) as a:
                a.extractall(tdir)
            roots = [p for p in tdir.iterdir() if p.is_dir()]
            if roots:
                roots[0].rename(local_path)
                _strip_vcs(local_path)
                shutil.rmtree(tdir, ignore_errors=True)
                zpath.unlink(missing_ok=True)
                return local_path
        except Exception as exc:
            print(f"[warn] zip dl failed: {exc}")
            shutil.rmtree(local_path, ignore_errors=True)
    return None


def _build_tree(repo_path, max_entries: int = 220) -> str:
    lines = []
    for i, p in enumerate(sorted(repo_path.rglob("*"))):
        if i >= max_entries:
            lines.append("...")
            break
        rel = p.relative_to(repo_path)
        if any(part.lower() in SKIP_DIRS for part in rel.parts):
            continue
        depth = len(rel.parts) - 1
        if depth > 3:
            continue
        lines.append(f"{'  ' * depth}{rel.name}{'/' if p.is_dir() else ''}")
    return "\n".join(lines)


def _find_readme(repo_path) -> str:
    for name in ("README.md", "README.rst", "readme.md"):
        p = repo_path / name
        if p.exists() and p.is_file():
            return _read_text(p, 40_000)
    return ""


def _collect_key_files(repo_path, max_files: int = 18) -> dict[str, str]:
    scored = []
    for p in repo_path.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(repo_path)
        if any(part.lower() in SKIP_DIRS for part in rel.parts):
            continue
        if p.stat().st_size > 350_000:
            continue
        stem = p.stem.lower()
        score = 0
        if stem in IMPORTANT_NAMES:
            score += 20
        if "src" in [x.lower() for x in rel.parts]:
            score += 10
        if p.suffix.lower() in {".py", ".ts", ".js", ".go", ".java"}:
            score += 8
        if len(rel.parts) <= 2:
            score += 5
        scored.append((score, p))
    return {str(p.relative_to(repo_path)): _read_text(p, 20_000)
            for _, p in sorted(scored, key=lambda x: (-x[0], str(x[1])))[:max_files]}


def compact_snapshot(snapshot: RepoSnapshot, max_chars: int = 38_000) -> str:
    import json as j
    meta = {"full_name": snapshot.candidate.full_name, "html_url": snapshot.candidate.html_url,
            "description": snapshot.candidate.description, "language": snapshot.candidate.language,
            "stars": snapshot.candidate.stars}
    files = "".join(f"\n--- {p} ---\n{c[:3500]}" for p, c in snapshot.key_files.items())
    text = f"METADATA:\n{j.dumps(meta, indent=2)}\n\nTREE:\n{snapshot.tree}\n\nREADME:\n{snapshot.readme[:9000]}\n{files}"
    return text[:max_chars]
