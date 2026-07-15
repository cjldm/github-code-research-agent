"""RAG-based code reading, analysis, and synthesis."""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from .embeddings import LocalHashEmbeddings
from .github import compact_snapshot, safe_dir_name
from .models import ProjectAnalysis, FinalRecommendation, QueryPlan, RepoSnapshot


def get_llm(model_env: str, temperature: float = 0):
    from langchain.chat_models import init_chat_model
    model_name = os.getenv(model_env, "deepseek-chat")
    provider = os.getenv("CHAT_MODEL_PROVIDER", "deepseek")
    kwargs = {"temperature": temperature}
    if provider.lower() == "deepseek" and os.getenv("DEEPSEEK_BASE_URL"):
        kwargs["base_url"] = os.getenv("DEEPSEEK_BASE_URL")
    if ":" in model_name:
        return init_chat_model(model_name, **kwargs)
    return init_chat_model(model_name, model_provider=provider, **kwargs)


async def structured_ainvoke(schema, model_env: str, system: str, user: str):
    llm = get_llm(model_env)
    return await llm.with_structured_output(schema).ainvoke([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])


def _should_read_file(path, skip_dirs) -> bool:
    if any(part.lower() in skip_dirs for part in path.parts):
        return False
    if path.stat().st_size > 350_000:
        return False
    TEXT_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs",
                       ".cpp", ".c", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
                       ".kt", ".scala", ".md", ".rst", ".txt", ".toml", ".yaml",
                       ".yml", ".json", ".ini", ".cfg", ".xml", ".html", ".css", ".sql"}
    IMPORTANT_NAMES = {"readme", "requirements", "pyproject", "setup", "package",
                       "build", "dockerfile", "makefile", "config", "main", "app",
                       "server", "cli", "train", "infer", "pipeline", "agent"}
    stem = path.stem.lower()
    return path.suffix.lower() in TEXT_EXTENSIONS or stem in IMPORTANT_NAMES


def iter_documents(repo_path: Path, skip_dirs: set) -> list[dict[str, str]]:
    from .github import _read_text as _rt
    docs = []
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if not _should_read_file(path, skip_dirs):
            continue
        text = _rt(path, 80_000)
        if text.strip():
            docs.append({"path": str(path.relative_to(repo_path)), "text": text})
    return docs


def build_or_load_retriever(snapshot: RepoSnapshot, index_dir: Path, skip_dirs: set):
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    repo_index = index_dir / safe_dir_name(snapshot.candidate.full_name)
    index_dir.mkdir(parents=True, exist_ok=True)
    ep = os.getenv("EMBEDDING_PROVIDER", "local_hash").lower()
    if ep == "openai":
        from langchain_openai import OpenAIEmbeddings
        embeddings = OpenAIEmbeddings(model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
    else:
        dims = int(os.getenv("LOCAL_HASH_EMBEDDING_DIMENSIONS", "1024"))
        embeddings = LocalHashEmbeddings(dimensions=dims)

    if repo_index.exists() and (repo_index / "index.faiss").exists() and (repo_index / "index.pkl").exists():
        vs = FAISS.load_local(str(repo_index), embeddings, allow_dangerous_deserialization=True)
        return vs.as_retriever(search_kwargs={"k": 8})
    if repo_index.exists():
        shutil.rmtree(repo_index, ignore_errors=True)

    raw_docs = iter_documents(snapshot.local_path, skip_dirs)
    splitter = RecursiveCharacterTextSplitter(chunk_size=1800, chunk_overlap=220)
    documents = []
    for raw in raw_docs:
        for i, chunk in enumerate(splitter.split_text(raw["text"])):
            documents.append(Document(
                page_content=chunk,
                metadata={"source": raw["path"], "chunk": i, "repo": snapshot.candidate.full_name},
            ))
    if not documents:
        documents = [Document(
            page_content=compact_snapshot(snapshot, 12_000),
            metadata={"source": "snapshot", "repo": snapshot.candidate.full_name},
        )]
    vs = FAISS.from_documents(documents, embeddings)
    repo_index.mkdir(parents=True, exist_ok=True)
    vs.save_local(str(repo_index))
    return vs.as_retriever(search_kwargs={"k": 8})


async def screen_snapshot(requirement: str, plan: QueryPlan, snapshot: RepoSnapshot):
    from .models import ScreeningDecision
    system = "You are a code repository screening agent. Exclude clearly irrelevant projects. Keep if potentially reusable."
    user = (f"User: {requirement}\nMust have: {plan.must_have}\nExclude: {plan.exclude_if}\n\n"
            f"Repo:\n{compact_snapshot(snapshot)}")
    try:
        return await structured_ainvoke(ScreeningDecision, "SCREEN_MODEL", system, user)
    except Exception as exc:
        print(f"[warn] screening failed: {exc}")
        score = 30
        text = f"{snapshot.candidate.full_name} {snapshot.readme[:2000]}".lower()
        for w in re.findall(r"[\w-]+", requirement.lower()):
            if len(w) > 3 and w in text:
                score += 5
        return ScreeningDecision(
            keep=score >= 45, relevance_score=min(score, 80),
            reason="Keywords fallback", method_guess="", mismatch_signals=[],
        )


async def analyze_project(requirement: str, snapshot: RepoSnapshot, index_dir: Path, skip_dirs: set) -> ProjectAnalysis:
    retriever = build_or_load_retriever(snapshot, index_dir, skip_dirs)
    queries = [f"{requirement} core algorithm", "project architecture entrypoint API",
               "input output data format dependencies", "limitations issues TODO"]
    seen, parts = set(), []
    for q in queries:
        for doc in await retriever.ainvoke(q):
            key = f"{doc.metadata.get('source', '')}:{doc.metadata.get('chunk', '')}"
            if key not in seen:
                seen.add(key)
                parts.append(f"[{doc.metadata['source']}]\n{doc.page_content[:1600]}")
    system = "Summarize method, code structure, reusable points, risks, fit score. Do not fabricate."
    user = (f"Requirement: {requirement}\nRepo: {snapshot.candidate.full_name}\nURL: {snapshot.candidate.html_url}\n"
            f"Tree:\n{snapshot.tree[:8000]}\n\nRAG:\n{'\n\n'.join(parts)[:42000]}")
    return await structured_ainvoke(ProjectAnalysis, "ANALYSIS_MODEL", system, user)


async def synthesize(requirement: str, analyses: list[ProjectAnalysis]) -> FinalRecommendation:
    system = "Output comparison table and recommend best solution from the project analyses."
    user = f"Requirement: {requirement}\n\n{json.dumps([a.model_dump() for a in analyses], ensure_ascii=False, indent=2)}"
    return await structured_ainvoke(FinalRecommendation, "ANALYSIS_MODEL", system, user)
