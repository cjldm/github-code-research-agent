"""Core data models for the GitHub Code Research Agent."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field


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
