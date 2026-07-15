"""Report generation utilities."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .models import FinalRecommendation, ProjectAnalysis, ProjectTableRow


def markdown_table(rows: list[ProjectTableRow]) -> str:
    headers = ["Project", "URL", "Fit Score", "Method", "Structure", "Conclusion"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        v = [re.sub(r"\s+", " ", x).replace("|", "\\|") for x in
             [row.project_name, row.address, str(row.fit_score),
              row.method, row.code_structure, row.conclusion]]
        lines.append("| " + " | ".join(v) + " |")
    return "\n".join(lines)


def write_reports(requirement: str, final: FinalRecommendation, analyses: list[ProjectAnalysis],
                  reports_dir: Path):
    stamp = time.strftime("%Y%m%d_%H%M%S")
    md = [
        "# GitHub Code Research Report",
        "", f"Requirement: {requirement}", "",
        "## Comparison Table", "", markdown_table(final.table), "",
        "## Best Solution", "", f"**{final.best_project}**", "", final.best_project_reason, "",
        "## Recommendation", "", final.recommended_code_solution, "",
        "## Steps", "", *[f"{i+1}. {s}" for i, s in enumerate(final.architecture_steps)], "",
        "## Next", "", *[f"{i+1}. {s}" for i, s in enumerate(final.next_actions)],
    ]
    md_path = reports_dir / f"report_{stamp}.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    json_path = reports_dir / f"report_{stamp}.json"
    json_path.write_text(
        json.dumps({"requirement": requirement, "final": final.model_dump(),
                     "analyses": [a.model_dump() for a in analyses]},
                    ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return md_path, json_path
