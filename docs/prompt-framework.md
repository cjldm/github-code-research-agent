# Prompt Framework

## Design Philosophy

The agent separates two concerns:

1. **LLM handles understanding** — translates vague requirements into structured fields
2. **Code handles execution** — generates precise GitHub queries, applies filters, controls scope

This prevents the model from expanding a specific task into generic domains.

## RequirementSpec Fields

| Field | Purpose | Who Fills |
|-------|---------|-----------|
| `raw_requirement` | Original user input | User / LLM |
| `domain` | Task domain | LLM |
| `target_object` | What the code processes | LLM |
| `task` | Action (classification, detection, etc.) | LLM |
| `modality` | Input type | LLM |
| `language` | Preferred programming language | LLM |
| `strict_terms` | Exact terms for primary search | LLM |
| `related_terms` | Adjacent tasks | LLM |
| `exclude_terms` | Clearly irrelevant categories | LLM |
| `allow_related` | Whether to include adjacent repos | User |

## LLM Expansion Rules

**Can expand:**
- Technical methods: CNN, ResNet, YOLO, OCR, RAG
- Related terms: facade segmentation for facade style recognition
- Exclude terms: generic courses, paper-only repos

**Cannot do:**
- Expand a specific task into generic ML courses
- Expand a vision task into LLM/agent/chatbot
- Drift from user's goal

## Search Layers

1. **Exact** — strict matches
2. **Synonym** — same task, different wording
3. **Adjacent** — related but different (only if allow_related=true)
