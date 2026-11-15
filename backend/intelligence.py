"""Universal intelligence / skill routing layer for NEXUS AI.

This module provides a *real* (non-hardcoded-response) capability router:
it inspects a user request, determines which NEXUS capabilities are relevant,
and returns the activated skill set plus a concrete execution plan. It never
fabricates answers; it only routes to existing backend modules.

Capabilities are registered in CAPABILITIES and can be extended without
rebuilding the engine.
"""
from __future__ import annotations

import re
from typing import Any

from .database import setting, read_bool


# Each capability maps to a real backend module/feature that already exists.
CAPABILITIES: list[dict[str, Any]] = [
    {
        "id": "conversation",
        "name": "Natural Conversation",
        "description": "Greeting, casual chat and contextual follow-up handling.",
        "module": "backend.native_brain / backend.llm",
        "available": True,
        "activation": [r"\b(hi|hello|hey|greetings|how are you|thanks|thank you)\b"],
        "inputs": {"message": "string"},
        "outputs": {"answer": "string"},
    },
    {
        "id": "knowledge_retrieval",
        "name": "Knowledge Retrieval",
        "description": "Semantic + lexical retrieval over learned knowledge, repos, web pages and skills.",
        "module": "backend.memory / backend.repos / backend.web_learn / backend.skills",
        "available": True,
        "activation": [r"\b(explain|what is|define|describe|tell me about|how does|why)\b",
                       r"\b(knowledge|remember|learned|repository|repo|web page)\b"],
        "inputs": {"query": "string"},
        "outputs": {"records": "list", "sources": "list"},
    },
    {
        "id": "reasoning",
        "name": "Reasoning & Problem Solving",
        "description": "Multi-step reasoning over retrieved context.",
        "module": "backend.agent / backend.llm",
        "available": True,
        "activation": [r"\b(analyze|reason|solve|compare|evaluate|why|how|explain)\b"],
        "inputs": {"problem": "string"},
        "outputs": {"analysis": "string"},
    },
    {
        "id": "coding",
        "name": "Coding & Software Development",
        "description": "Code generation, debugging, refactoring, testing across many languages.",
        "module": "backend.programmer / backend.sandbox / backend.review / backend.projects",
        "available": True,
        "activation": [r"\b(code|program|script|function|class|api|website|app|debug|refactor|test)\b",
                       r"\b(python|javascript|typescript|java|c\+\+|rust|go|php|sql|html|css)\b",
                       r"\b(write|build|create|generate|implement)\b.*\b(program|code|app|website|api)\b"],
        "inputs": {"request": "string", "language": "string?"},
        "outputs": {"files": "list", "verification": "object"},
    },
    {
        "id": "web_research",
        "name": "Web Research",
        "description": "Public HTTPS fetching, crawling and URL learning.",
        "module": "backend.web_learn / backend.research / backend.tools",
        "available": True,
        "activation": [r"\b(research|search the web|fetch|url|website|article|learn url)\b",
                       r"https?://"],
        "inputs": {"query_or_url": "string"},
        "outputs": {"sources": "list", "chunks": "list"},
    },
    {
        "id": "autonomous_agents",
        "name": "Autonomous Agents",
        "description": "Multi-step task execution, planning and self-improvement.",
        "module": "backend.agent / backend.autonomous / backend.autoprogramming",
        "available": True,
        "activation": [r"\b(agent|autonomous|task|objective|plan|execute)\b"],
        "inputs": {"objective": "string"},
        "outputs": {"task_id": "int", "status": "string"},
    },
    {
        "id": "memory",
        "name": "Memory & Experience",
        "description": "Short/long-term memory retrieval and storage.",
        "module": "backend.memory",
        "available": True,
        "activation": [r"\b(remember|memory|experience|lesson|previous|earlier|context)\b"],
        "inputs": {"query": "string"},
        "outputs": {"memories": "list"},
    },
    {
        "id": "math",
        "name": "Mathematical Reasoning",
        "description": "Math evaluation and reasoning (safe AST evaluator).",
        "module": "backend.agents (mathematics)",
        "available": True,
        "activation": [r"\b(math|calculate|compute|equation|integral|derivative|gcd|factorial)\b",
                       r"\d+\s*[\+\-\*/\^]\s*\d+"],
        "inputs": {"expression": "string"},
        "outputs": {"result": "string"},
    },
    {
        "id": "document_processing",
        "name": "Document Processing",
        "description": "Reading, chunking and summarizing documents.",
        "module": "backend.web_learn / backend.repos / backend.tools.read_file",
        "available": True,
        "activation": [r"\b(document|pdf|file|read file|summarize document|analyze document)\b"],
        "inputs": {"path_or_url": "string"},
        "outputs": {"summary": "string"},
    },
    {
        "id": "image_understanding",
        "name": "Image Understanding",
        "description": "Describe/analyze images (requires a vision-capable model or tool).",
        "module": "backend.providers (vision-capable models)",
        "available": False,
        "activation": [r"\b(analyze image|describe image|what is in (this|the) image|image understanding)\b",
                       r"\banalyze\b.*\bimage\b", r"\bimage\b.*\banalyze\b"],
        "inputs": {"image": "file"},
        "outputs": {"description": "string"},
        "note": "Requires a vision-capable provider; not bundled by default.",
    },
    {
        "id": "image_generation",
        "name": "Image Generation",
        "description": "Generate images from text prompts (requires configured image service).",
        "module": "backend (configurable image provider)",
        "available": False,
        "activation": [r"\b(generate|create|draw|make)\b.*\b(image|picture|illustration|logo|art)\b",
                       r"\b(image|picture)\b.*\b(generate|create|draw)\b"],
        "inputs": {"prompt": "string"},
        "outputs": {"image_path": "string"},
        "note": "Requires an image-generation service/API configured in Settings.",
    },
]


def classify_intent(message: str) -> dict[str, Any]:
    text = (message or "").strip()
    activated = []
    for cap in CAPABILITIES:
        for pat in cap.get("activation", []):
            if re.search(pat, text, re.I):
                activated.append(cap)
                break
    # Always include conversation + knowledge retrieval as baseline when nothing else.
    if not activated:
        ids = {"conversation", "knowledge_retrieval"}
        activated = [c for c in CAPABILITIES if c["id"] in ids]
    # De-duplicate preserving order
    seen = set()
    unique = []
    for c in activated:
        if c["id"] not in seen:
            seen.add(c["id"])
            unique.append(c)
    # Determine availability / missing dependencies
    missing = [c["id"] for c in unique if not c.get("available", True)]
    plan = []
    for c in unique:
        plan.append({"capability": c["id"], "action": f"activate:{c['module']}"})
    return {
        "message": text,
        "activated": [{"id": c["id"], "name": c["name"], "module": c["module"],
                       "available": c.get("available", True)} for c in unique],
        "missing_capabilities": missing,
        "execution_plan": plan,
        "multi_skill": len(unique) > 1,
    }


def skill_registry() -> list[dict[str, Any]]:
    out = []
    for c in CAPABILITIES:
        out.append({
            "id": c["id"],
            "name": c["name"],
            "description": c["description"],
            "module": c["module"],
            "available": c.get("available", True),
            "inputs": c.get("inputs", {}),
            "outputs": c.get("outputs", {}),
            "note": c.get("note"),
        })
    return out


def available_skills_count() -> int:
    return sum(1 for c in CAPABILITIES if c.get("available", True))
