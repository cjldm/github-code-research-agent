from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
import warnings
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from pydantic import BaseModel, Field


warnings.filterwarnings("ignore", message="`langchain-community` is being sunset.*", category=DeprecationWarning)

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
WORKSPACE = ROOT / "workspace"
REPOS_DIR = WORKSPACE / "repos"
REPORTS_DIR = WORKSPACE / "reports"
INDEX_DIR = Path(os.getenv("AGENT_INDEX_DIR", Path.home() / ".github_code_agent_cache" / "indexes"))

TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    ".m",
    ".mm",
    ".r",
    ".jl",
    ".sh",
    ".ps1",
    ".md",
    ".rst",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".ini",
    ".cfg",
    ".xml",
    ".html",
    ".css",
    ".sql",
}

IMPORTANT_NAMES = {
    "readme",
    "requirements",
    "pyproject",
    "setup",
    "package",
    "pom",
    "build",
    "dockerfile",
    "makefile",
    "environment",
    "config",
    "main",
    "app",
    "server",
    "cli",
    "train",
    "infer",
    "pipeline",
    "agent",
}

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".turbo",
    ".cache",
    "target",
    "vendor",
    "data",
    "datasets",
    "checkpoints",
    "weights",
}


class QueryPlan(BaseModel):
    search_queries: list[str] = Field(description="GitHub search queries")
    must_have: list[str] = Field(description="Capabilities that relevant projects should have")
    exclude_if: list[str] = Field(description="Signals that indicate an irrelevant project")
    preferred_languages: list[str] = Field(default_factory=list)


class RequirementSpec(BaseModel):
    raw_requirement: str
    domain: str = ""
    target_object: list[str] = Field(default_factory=list)
    task: list[str] = Field(default_factory=list)
    modality: list[str] = Field(default_factory=list)
    language: list[str] = Field(default_factory=lambda: ["Python"])
    strict_terms: list[str] = Field(default_factory=list)
    technical_methods: list[str] = Field(default_factory=list)
    allow_related: bool = True
    related_terms: list[str] = Field(default_factory=list)
    exclude_terms: list[str] = Field(default_factory=list)
    min_projects: int = 6
    max_results: int = 20
    keep: int = 8


class ScreeningDecision(BaseModel):
    keep: bool
    relevance_score: int = Field(ge=0, le=100)
    reason: str
    method_guess: str
    mismatch_signals: list[str] = Field(default_factory=list)


class ProjectAnalysis(BaseModel):
    project_name: str
    address: str
    fit_score: int = Field(ge=0, le=100)
    method: str
    code_structure: str
    core_files: list[str]
    strengths: list[str]
    weaknesses: list[str]
    reusable_ideas: list[str]
    implementation_risks: list[str]
    evidence: list[str]


class ProjectTableRow(BaseModel):
    project_name: str
    address: str
    fit_score: int
    method: str
    code_structure: str
    conclusion: str


class FinalRecommendation(BaseModel):
    table: list[ProjectTableRow]
    best_project: str
    best_project_reason: str
    recommended_code_solution: str
    architecture_steps: list[str]
    rag_enhancement_plan: list[str]
    next_actions: list[str]


@dataclass
class RepoCandidate:
    full_name: str
    html_url: str
    clone_url: str
    description: str
    language: str
    stars: int
    forks: int
    updated_at: str
    default_branch: str = "main"


@dataclass
class RepoSnapshot:
    candidate: RepoCandidate
    local_path: Path
    tree: str
    readme: str
    key_files: dict[str, str]


def ensure_dirs() -> None:
    for path in (WORKSPACE, REPOS_DIR, REPORTS_DIR, INDEX_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_langchain_or_exit() -> None:
    missing: list[str] = []
    for module, package in [
        ("langchain_deepseek", "langchain-deepseek"),
        ("langchain_text_splitters", "langchain-text-splitters"),
        ("langchain_community", "langchain-community"),
        ("langchain", "langchain"),
    ]:
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        joined = " ".join(sorted(set(missing)))
        raise SystemExit(
            "Current Python environment is missing LangChain dependencies. Please run:\n"
            f"python -m pip install {joined}\n"
            "or: python -m pip install -r requirements.txt"
        )


def get_llm(model_env: str, temperature: float = 0):
    from langchain.chat_models import init_chat_model

    model_name = os.getenv(model_env, "deepseek-chat")
    provider = os.getenv("CHAT_MODEL_PROVIDER", "deepseek")
    kwargs: dict[str, Any] = {"temperature": temperature}
    if provider.lower() == "deepseek" and os.getenv("DEEPSEEK_BASE_URL"):
        kwargs["base_url"] = os.getenv("DEEPSEEK_BASE_URL")
    if ":" in model_name:
        return init_chat_model(model_name, **kwargs)
    return init_chat_model(model_name, model_provider=provider, **kwargs)


class LocalHashEmbeddings(Embeddings):
    """Small deterministic embeddings for offline code RAG."""

    def __init__(self, dimensions: int = 1024):
        self.dimensions = dimensions

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}|[一-鿿]{1,}", text.lower())
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def __call__(self, text: str) -> list[float]:
        return self.embed_query(text)


async def structured_ainvoke(schema: type[BaseModel], model_env: str, system: str, user: str):
    llm = get_llm(model_env)
    structured = llm.with_structured_output(schema)
    return await structured.ainvoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )


def contains_cjk(text: str) -> bool:
    return any("一" <= char <= "鿿" for char in text)


def parse_requirement_spec(requirement: str) -> RequirementSpec:
    raw = requirement.strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            ...
        except Exception:
            pass
    return RequirementSpec(raw_requirement=raw, strict_terms=[raw], exclude_terms=["course notes only", "no source code"])


def validate_runtime_config() -> None:
    provider = os.getenv("CHAT_MODEL_PROVIDER", "deepseek").lower()
    if provider == "deepseek" and not os.getenv("DEEPSEEK_API_KEY"):
        raise SystemExit("Missing DEEPSEEK_API_KEY.")


async def main():
    # CLI entry point
    validate_runtime_config()
    ...


if __name__ == "__main__":
    asyncio.run(main())
