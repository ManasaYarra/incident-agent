"""
Member 2 — Incident Command Center
AI-powered incident memory and response (Streamlit + Groq + memory.py)
"""

from __future__ import annotations

import os
import re
import time
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from groq import Groq

from memory import find_similar, save_incident

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_FILE, override=True)


def get_groq_api_key() -> str:
    load_dotenv(dotenv_path=ENV_FILE, override=True)
    return os.getenv("GROQ_API_KEY", "").strip()


GROQ_MODEL = "openai/gpt-oss-120b"

ANALYSIS_STAGES = [
    ("SCANNING INCIDENT...", None),
    ("SEARCHING MEMORY...", "memory"),
    ("ANALYZING PATTERNS...", None),
    ("CONSULTING AI...", "groq"),
    ("GENERATING RESPONSE...", None),
]

SEVERITY_OPTIONS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

# Flexible field access for Member 3 datasets
_LOG_KEYS = ("log", "incident_log", "incident", "error_log", "text")
_FIX_KEYS = ("fix", "recommended_fix", "solution", "resolution")
_ROOT_CAUSE_KEYS = ("root_cause", "root cause", "cause")


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


def init_session_state() -> None:
    defaults = {
        "current_log": "",
        "current_answer": "",
        "current_root_cause": "",
        "similar_incidents": [],
        "ai_sections": None,
        "analysis_complete": False,
        "feedback_message": None,
        "feedback_type": None,
        "last_error": None,
        "last_warning": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def extract_similar_list(similar: Any) -> list[Any]:
    """Safely unwrap Hindsight RecallResponse, lists, or custom iterables."""
    if not similar:
        return []
    if hasattr(similar, "results"):
        return list(similar.results)
    if isinstance(similar, list):
        return similar
    if hasattr(similar, "__iter__") and not isinstance(similar, (str, bytes)):
        return list(similar)
    return [similar]


def normalize_memory_item(item: Any) -> dict[str, str]:
    """
    Extract log, root_cause, fix, and outcome from Hindsight RecallResult objects,
    structured dicts, or plain text strings.
    """
    if hasattr(item, "text"):
        raw_text = str(item.text)
    elif isinstance(item, dict):
        raw_text = str(item.get("text") or item.get("log") or item.get("incident") or "")
    else:
        raw_text = str(item)

    log = raw_text
    root_cause = ""
    fix = ""
    outcome = ""

    # Check dict keys if available
    if isinstance(item, dict):
        log = item.get("log") or item.get("incident_log") or item.get("incident") or raw_text
        root_cause = item.get("root_cause") or item.get("cause") or ""
        fix = item.get("fix") or item.get("solution") or item.get("recommended_fix") or ""
        outcome = str(item.get("outcome") or "")

    # Parse formatted text blocks (e.g. Error: ... Root cause: ... Fix: ... Outcome: ...)
    for line in raw_text.splitlines():
        line_s = line.strip()
        lower = line_s.lower()
        if lower.startswith("error:"):
            log = line_s[6:].strip()
        elif lower.startswith("root cause:") or lower.startswith("cause:"):
            root_cause = line_s.split(":", 1)[1].strip()
        elif lower.startswith("fix:") or lower.startswith("solution:"):
            fix = line_s.split(":", 1)[1].strip()
        elif lower.startswith("outcome:"):
            outcome = line_s.split(":", 1)[1].strip()

    # If outcome is not explicitly tagged, infer from sentiment or default to recorded
    if not outcome:
        lower_raw = raw_text.lower()
        if "failed" in lower_raw or "avoid" in lower_raw:
            outcome = "failed"
        elif "worked" in lower_raw or "resolved" in lower_raw or "executed" in lower_raw or "success" in lower_raw:
            outcome = "worked"
        else:
            outcome = "recorded"

    return {
        "log": log or raw_text,
        "root_cause": root_cause,
        "fix": fix or raw_text,
        "outcome": outcome.lower(),
        "raw_text": raw_text,
    }


def get_groq_client() -> Groq | None:
    api_key = get_groq_api_key()
    if not api_key:
        return None
    try:
        return Groq(api_key=api_key)
    except Exception:
        return None


def format_similar_for_prompt(similar: Any) -> str:
    items = [normalize_memory_item(x) for x in extract_similar_list(similar)]
    if not items:
        return "No similar past incidents found in memory."

    blocks: list[str] = []
    for index, item in enumerate(items[:5], start=1):
        outcome = item.get("outcome", "recorded")
        log_val = item.get("log", "")
        if len(log_val) > 400:
            log_val = log_val[:400] + "..."
        blocks.append(
            "\n".join(
                [
                    f"Incident {index}:",
                    f"  Log/Fact: {log_val or item.get('raw_text', 'N/A')}",
                    f"  Root cause: {item.get('root_cause') or 'N/A'}",
                    f"  Fix: {item.get('fix') or 'N/A'}",
                    f"  Outcome: {outcome}",
                ]
            )
        )
    return "\n\n".join(blocks)


def parse_ai_response(raw_text: str) -> dict[str, str]:
    """
    Parse structured sections (LIKELY ROOT CAUSE, RECOMMENDED FIX, PRECAUTIONS)
    from the model response. Robust against markdown symbols, asterisks, numbering,
    and inline bodies.
    """
    cleaned = raw_text.strip()
    sections = {
        "root_cause": "",
        "recommended_fix": "",
        "precautions": "",
        "raw": cleaned,
    }

    # Matches headers like:
    # **LIKELY ROOT CAUSE**
    # ### 1. LIKELY ROOT CAUSE:
    # **RECOMMENDED FIX:** Optional inline text
    header_regex = re.compile(
        r"^\s*[#*_-]*(?:\d+[\.\)])?\s*\*{0,2}(LIKELY\s+ROOT\s+CAUSE|ROOT\s+CAUSE|RECOMMENDED\s+FIX|FIX|PRECAUTIONS?|PRECAUTIONARY\s+STEPS?)\*{0,2}\s*:?\s*(.*)$",
        re.IGNORECASE,
    )

    def normalize_header(h: str) -> str:
        h_clean = re.sub(r"[^A-Z\s]", "", h.upper()).strip()
        if "ROOT CAUSE" in h_clean:
            return "root_cause"
        if "FIX" in h_clean:
            return "recommended_fix"
        if "PRECAUTION" in h_clean:
            return "precautions"
        return ""

    lines = cleaned.splitlines()
    current_key: str | None = None
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        match = header_regex.match(stripped)
        if match and match.group(1):
            if current_key:
                sections[current_key] = "\n".join(current_lines).strip()
                current_lines = []
            current_key = normalize_header(match.group(1))
            inline_body = match.group(2).strip()
            if inline_body:
                inline_body = re.sub(r"^\*{1,2}\s*", "", inline_body)
                current_lines.append(inline_body)
        elif current_key:
            current_lines.append(line)
        else:
            current_lines.append(line)

    if current_key and current_lines:
        sections[current_key] = "\n".join(current_lines).strip()
    elif not current_key and current_lines:
        sections["raw"] = "\n".join(current_lines).strip()

    # Fallback if no sections detected
    if not any(sections[k] for k in ("root_cause", "recommended_fix", "precautions")):
        sections["root_cause"] = cleaned

    return sections


def analyze_with_groq(log: str, similar: Any) -> dict[str, str]:
    client = get_groq_client()
    if client is None:
        raise RuntimeError(
            "Groq API key is not configured. Add GROQ_API_KEY to your .env file."
        )

    norm_items = [normalize_memory_item(x) for x in extract_similar_list(similar)]
    failed_fixes = [
        item.get("fix")
        for item in norm_items
        if item.get("outcome") == "failed" and item.get("fix")
    ]

    system_prompt = (
        "You are an on-call engineering assistant. Analyze incidents, identify likely "
        "root causes, recommend practical fixes, and mention useful precautions.\n"
        "Use historical incidents as memory/context when provided.\n"
        "Clearly distinguish historical information from your own recommendation.\n"
        "Do not invent historical incidents.\n"
        "If a previous fix is marked FAILED, do not recommend that same failed approach again.\n\n"
        "Structure your answer with these exact headings:\n"
        "LIKELY ROOT CAUSE\n"
        "RECOMMENDED FIX\n"
        "PRECAUTIONS"
    )

    failed_fixes_block = (
        "\n".join(f"- {fix}" for fix in failed_fixes)
        if failed_fixes
        else "- None recorded"
    )

    user_prompt = f"""NEW INCIDENT:
{log}

SIMILAR PAST INCIDENTS:
{format_similar_for_prompt(similar)}

Failed fixes to avoid (from memory):
{failed_fixes_block}
"""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=1500,
    )

    content = (response.choices[0].message.content or "").strip()
    if not content:
        reasoning = getattr(response.choices[0].message, "reasoning", "")
        if reasoning:
            content = reasoning.strip()
        else:
            raise RuntimeError("Groq returned an empty response. Please retry.")

    return parse_ai_response(content)


# ---------------------------------------------------------------------------
# UI styling
# ---------------------------------------------------------------------------


def inject_global_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=Inter:wght@400;500;600;700&display=swap');
        :root {
            --glass: rgba(14, 22, 38, 0.78);
            --cyan: #00d4ff;
            --green: #00ff9d;
            --red: #ff4d6d;
            --amber: #ffb020;
            --muted: #8fa3bf;
        }
        .stApp {
            background:
                radial-gradient(circle at 12% 8%, rgba(0, 212, 255, 0.07), transparent 26%),
                radial-gradient(circle at 88% 2%, rgba(0, 255, 157, 0.05), transparent 22%),
                linear-gradient(180deg, #04070f 0%, #060a12 50%, #050910 100%);
            font-family: 'Inter', sans-serif;
            color: #e8eef7;
        }
        #MainMenu, footer, header { visibility: hidden; height: 0; }
        .block-container { padding-top: 1rem; padding-bottom: 2.5rem; max-width: 1180px; }
        .panel {
            margin-top: 1rem;
            padding: 1.15rem 1.25rem;
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.08);
            background: var(--glass);
            backdrop-filter: blur(10px);
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
        }
        .panel-title {
            font-family: 'Orbitron', sans-serif;
            letter-spacing: 0.12em;
            font-size: 0.95rem;
            color: var(--cyan);
            margin-bottom: 0.75rem;
        }
        .hero {
            padding: 1.4rem 1.6rem;
            border-radius: 18px;
            border: 1px solid rgba(0, 212, 255, 0.22);
            background: linear-gradient(135deg, rgba(8,16,30,0.94), rgba(10,20,36,0.78));
            box-shadow: 0 18px 50px rgba(0,0,0,0.35);
            margin-bottom: 0.5rem;
        }
        .hero-title {
            font-family: 'Orbitron', sans-serif;
            font-size: clamp(1.4rem, 2.8vw, 2.1rem);
            letter-spacing: 0.1em;
            margin: 0;
        }
        .hero-sub { color: var(--muted); margin-top: 0.35rem; }
        .status-row {
            display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 0.9rem;
        }
        .status-pill {
            display: inline-flex; align-items: center; gap: 0.45rem;
            padding: 0.4rem 0.75rem; border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.1);
            background: rgba(255,255,255,0.03);
            font-size: 0.78rem; letter-spacing: 0.08em;
        }
        .dot {
            width: 8px; height: 8px; border-radius: 50%;
            animation: pulse 1.8s ease-in-out infinite;
        }
        .dot-green { background: var(--green); box-shadow: 0 0 10px var(--green); }
        .dot-amber { background: var(--amber); box-shadow: 0 0 10px var(--amber); }
        .dot-red { background: var(--red); box-shadow: 0 0 10px var(--red); }
        @keyframes pulse {
            0%,100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.3); opacity: 0.65; }
        }
        .scan-box {
            padding: 0.85rem 1rem; border-radius: 12px;
            border: 1px dashed rgba(0,212,255,0.35);
            background: rgba(0,212,255,0.05);
            color: #b8ecff; font-family: Orbitron, sans-serif;
            letter-spacing: 0.08em;
            animation: scanGlow 1.5s ease-in-out infinite;
        }
        @keyframes scanGlow {
            0%,100% { box-shadow: none; }
            50% { box-shadow: 0 0 16px rgba(0,212,255,0.15); }
        }
        .response-card {
            padding: 0.95rem 1.05rem; border-radius: 14px;
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.02);
            margin-bottom: 0.75rem;
        }
        .response-card h4 {
            margin: 0 0 0.5rem 0; color: var(--cyan);
            font-family: Orbitron, sans-serif; letter-spacing: 0.1em; font-size: 0.8rem;
        }
        .badge-ok {
            color: var(--green); background: rgba(0,255,157,0.12);
            border: 1px solid rgba(0,255,157,0.35);
            padding: 0.2rem 0.5rem; border-radius: 999px; font-size: 0.72rem; font-weight: 700;
        }
        .badge-bad {
            color: var(--red); background: rgba(255,77,109,0.12);
            border: 1px solid rgba(255,77,109,0.35);
            padding: 0.2rem 0.5rem; border-radius: 999px; font-size: 0.72rem; font-weight: 700;
        }
        .feedback-ok, .feedback-bad {
            padding: 0.9rem 1rem; border-radius: 12px; margin-top: 0.75rem; font-weight: 600;
        }
        .feedback-ok { color: var(--green); border: 1px solid rgba(0,255,157,0.35); background: rgba(0,255,157,0.08); }
        .feedback-bad { color: #ffc2cf; border: 1px solid rgba(255,77,109,0.35); background: rgba(255,77,109,0.08); }
        .sidebar-card {
            padding: 0.8rem; border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.03); margin-bottom: 0.7rem;
        }
        .sidebar-k { color: var(--muted); font-size: 0.72rem; letter-spacing: 0.1em; text-transform: uppercase; }
        .sidebar-v { color: #eef6ff; font-weight: 600; margin-top: 0.2rem; }
        div[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #070d18 0%, #0a1322 100%);
            border-right: 1px solid rgba(0,212,255,0.12);
        }
        .stTextArea textarea, .stTextInput input {
            background: rgba(255,255,255,0.03) !important;
            color: #edf4ff !important;
            border: 1px solid rgba(255,255,255,0.12) !important;
            border-radius: 12px !important;
        }
        .stButton > button {
            border-radius: 12px !important;
            border: 1px solid rgba(0,212,255,0.35) !important;
            background: linear-gradient(135deg, rgba(0,212,255,0.18), rgba(0,255,157,0.12)) !important;
            color: #f4fbff !important; font-weight: 700 !important;
            letter-spacing: 0.06em !important;
            transition: all 0.25s ease !important;
        }
        .stButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 0 16px rgba(0,212,255,0.22);
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, rgba(0,212,255,0.35), rgba(0,255,157,0.22)) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_ai_core() -> None:
    components.html(
        """
        <!DOCTYPE html><html><head><style>
        body { margin:0; background:transparent; overflow:hidden; font-family:Inter,sans-serif; }
        .wrap { position:relative; height:220px; display:flex; align-items:center; justify-content:center; }
        .scene { position:relative; width:170px; height:170px; transform-style:preserve-3d; animation:float 4s ease-in-out infinite; }
        @keyframes float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-8px)} }
        .ring { position:absolute; inset:0; border-radius:50%; border:1px solid rgba(0,212,255,0.35); box-shadow:0 0 20px rgba(0,212,255,0.12); }
        .r1 { animation:spin1 8s linear infinite; transform:rotateX(68deg); }
        .r2 { animation:spin2 11s linear infinite; transform:rotateY(62deg); border-color:rgba(0,255,157,0.35); }
        .r3 { animation:spin3 14s linear infinite; transform:rotateX(35deg) rotateY(35deg); }
        @keyframes spin1 { from{transform:rotateX(68deg) rotateZ(0)} to{transform:rotateX(68deg) rotateZ(360deg)} }
        @keyframes spin2 { from{transform:rotateY(62deg) rotateZ(0)} to{transform:rotateY(62deg) rotateZ(360deg)} }
        @keyframes spin3 { from{transform:rotateX(35deg) rotateY(35deg) rotateZ(0)} to{transform:rotateX(35deg) rotateY(35deg) rotateZ(360deg)} }
        .core { position:absolute; inset:50px; border-radius:50%;
            background:radial-gradient(circle at 35% 30%, #7dfcff, #007ea8 45%, #03111d 80%);
            box-shadow:0 0 30px rgba(0,212,255,0.5); animation:pulse 2.4s ease-in-out infinite; }
        @keyframes pulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.05)} }
        .node { position:absolute; width:8px; height:8px; border-radius:50%; background:#00ff9d; box-shadow:0 0 8px #00ff9d; animation:drift 5s linear infinite; }
        .n1{top:18%;left:10%} .n2{top:68%;left:16%;background:#00d4ff;box-shadow:0 0 8px #00d4ff;animation-delay:1s}
        .n3{top:28%;right:8%;animation-delay:2s} .n4{bottom:14%;right:20%;background:#ffb020;box-shadow:0 0 8px #ffb020;animation-delay:0.7s}
        @keyframes drift { 0%,100%{opacity:.25;transform:translate(0,0)} 50%{opacity:1;transform:translate(6px,-10px)} }
        .flow { position:absolute; bottom:6px; width:100%; text-align:center; color:#8fa3bf; font-size:10px; letter-spacing:.16em; }
        </style></head><body>
        <div class="wrap">
            <div class="node n1"></div><div class="node n2"></div><div class="node n3"></div><div class="node n4"></div>
            <div class="scene">
                <div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="core"></div>
            </div>
            <div class="flow">INCIDENT → MEMORY → AI → RESPONSE</div>
        </div></body></html>
        """,
        height=225,
    )


def render_pipeline(active_step: int = 0) -> None:
    steps = ["INCIDENT", "MEMORY", "GROQ AI", "RESPONSE"]
    parts: list[str] = []
    for i, step in enumerate(steps, start=1):
        cls = "active" if i <= active_step else ""
        parts.append(f'<div class="pipe-node {cls}">{step}</div>')
        if i < len(steps):
            line_cls = "active" if i < active_step else ""
            parts.append(f'<div class="pipe-line {line_cls}"></div>')

    st.markdown(
        f"""
        <style>
        .pipeline {{ display:flex; align-items:center; justify-content:center; flex-wrap:wrap; gap:.3rem; margin:.6rem 0; }}
        .pipe-node {{
            min-width:108px; padding:.65rem .75rem; border-radius:12px; text-align:center;
            border:1px solid rgba(255,255,255,0.08); background:rgba(255,255,255,0.02);
            color:#8fa3bf; font-family:Orbitron,sans-serif; font-size:.7rem; letter-spacing:.08em;
            transition:all .35s ease;
        }}
        .pipe-node.active {{
            color:#e8f7ff; border-color:rgba(0,212,255,0.45);
            box-shadow:0 0 14px rgba(0,212,255,0.16); background:rgba(0,212,255,0.08);
            animation:nodePulse 2s ease-in-out infinite;
        }}
        @keyframes nodePulse {{ 0%,100%{{transform:translateY(0)}} 50%{{transform:translateY(-2px)}} }}
        .pipe-line {{ width:30px; height:2px; background:rgba(255,255,255,0.08); }}
        .pipe-line.active {{ background:linear-gradient(90deg,rgba(0,212,255,.2),rgba(0,255,157,.8)); animation:flow 1.4s linear infinite; }}
        @keyframes flow {{ 0%,100%{{opacity:.45}} 50%{{opacity:1}} }}
        </style>
        <div class="pipeline">{''.join(parts)}</div>
        """,
        unsafe_allow_html=True,
    )


def render_architecture() -> None:
    layers = [
        ("USER INTERFACE", "Streamlit UI Console & Dashboard"),
        ("INCIDENT INPUT", "Error Log Ingestion & Parameter Tagging"),
        ("MEMORY RECALL", "Historical Search via find_similar()"),
        ("GROQ AI", "Root Cause Analysis & Fix Generation (openai/gpt-oss-120b)"),
        ("USER FEEDBACK", "Operator Resolution Feedback (Worked / Failed)"),
        ("MEMORY UPDATE", "Persistent Feedback Storage via save_incident()"),
    ]
    cards: list[str] = []
    for idx, (title, subtitle) in enumerate(layers, start=1):
        cards.append(
            f'<div class="arch-layer">'
            f'<div class="arch-title"><span class="arch-badge">0{idx}</span> {title}</div>'
            f'<div class="arch-sub">{subtitle}</div>'
            f'</div>'
        )
        if idx < len(layers):
            cards.append('<div class="arch-arrow">↓</div>')

    content_html = "".join(cards)

    st.markdown(
        f"""<style>
.arch-stack {{ perspective: 900px; max-width: 720px; margin: 0 auto; }}
.arch-layer {{
    margin: 0 auto 0.25rem auto; padding: 0.85rem 1.1rem; border-radius: 14px;
    border: 1px solid rgba(0, 212, 255, 0.25);
    background: linear-gradient(135deg, rgba(12, 22, 42, 0.85) 0%, rgba(8, 16, 32, 0.7) 100%);
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.3); text-align: center;
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}}
.arch-layer:hover {{ transform: translateY(-2px); box-shadow: 0 14px 30px rgba(0, 212, 255, 0.15); }}
.arch-badge {{
    display: inline-block; font-size: 0.68rem; color: #00d4ff;
    background: rgba(0, 212, 255, 0.12); border: 1px solid rgba(0, 212, 255, 0.35);
    padding: 0.1rem 0.45rem; border-radius: 6px; margin-right: 0.4rem;
}}
.arch-title {{ font-family: Orbitron, sans-serif; letter-spacing: 0.1em; font-size: 0.82rem; color: #ffffff; font-weight: 700; }}
.arch-sub {{ color: #8fa3bf; font-size: 0.76rem; margin-top: 0.25rem; }}
.arch-arrow {{ text-align: center; color: #00d4ff; margin: 0.15rem 0; font-size: 1.15rem; font-weight: 700; text-shadow: 0 0 8px rgba(0, 212, 255, 0.6); }}
</style>
<div class="arch-stack">
{content_html}
</div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------


def ai_engine_status() -> tuple[str, str]:
    if not get_groq_api_key():
        return "ERROR", "dot-red"
    if get_groq_client() is None:
        return "ERROR", "dot-red"
    return "READY", "dot-green"


def memory_engine_status() -> tuple[str, str]:
    try:
        from memory import memory_is_available

        if memory_is_available():
            return "READY", "dot-green"
    except Exception:
        pass
    return "ERROR", "dot-red"


# ---------------------------------------------------------------------------
# UI sections
# ---------------------------------------------------------------------------


def render_header() -> None:
    ai_status, ai_dot = ai_engine_status()
    mem_status, mem_dot = memory_engine_status()

    st.markdown(
        f"""
        <div class="hero">
            <h1 class="hero-title">🚨 INCIDENT COMMAND CENTER</h1>
            <div class="hero-sub">AI-powered incident memory and response</div>
            <div class="status-row">
                <div class="status-pill"><span class="dot {ai_dot}"></span> AI ENGINE · {ai_status}</div>
                <div class="status-pill"><span class="dot {mem_dot}"></span> MEMORY ENGINE · {mem_status}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> None:
    ai_status, ai_dot = ai_engine_status()
    mem_status, mem_dot = memory_engine_status()

    incident_state = "READY" if st.session_state.get("current_log") else "NOT ANALYZED"
    response_state = (
        "READY" if st.session_state.get("analysis_complete") else "NOT GENERATED"
    )

    with st.sidebar:
        st.markdown("### 🚨 INCIDENT COMMAND")
        st.markdown("#### SYSTEM STATUS")
        st.markdown(
            f"""
            <div class="sidebar-card">
                <div class="sidebar-k">AI ENGINE</div>
                <div class="sidebar-v"><span class="dot {ai_dot}" style="display:inline-block;margin-right:6px;"></span>{ai_status}</div>
                <div class="sidebar-k" style="margin-top:.7rem;">MEMORY</div>
                <div class="sidebar-v"><span class="dot {mem_dot}" style="display:inline-block;margin-right:6px;"></span>{mem_status}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("#### CURRENT SESSION")
        st.markdown(
            f"""
            <div class="sidebar-card">
                <div class="sidebar-k">Incident</div>
                <div class="sidebar-v">{incident_state}</div>
                <div class="sidebar-k" style="margin-top:.7rem;">AI Response</div>
                <div class="sidebar-v">{response_state}</div>
                <div class="sidebar-k" style="margin-top:.7rem;">Memory Bank</div>
                <div class="sidebar-v" style="font-size:0.78rem;color:#00ff9d;">Hindsight (incident-response)</div>
                <div class="sidebar-k" style="margin-top:.7rem;">Groq Model</div>
                <div class="sidebar-v" style="font-size:0.78rem;color:#00d4ff;">openai/gpt-oss-120b</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_incident_input() -> tuple[str, str, str, bool]:
    st.markdown('<div class="panel"><div class="panel-title">NEW INCIDENT</div>', unsafe_allow_html=True)

    log = st.text_area(
        "Paste error log here",
        height=180,
        placeholder="Paste error log here",
        label_visibility="collapsed",
        key="incident_input_area",
    )

    cols = st.columns([0.75, 1, 1.25])
    with cols[0]:
        severity = st.selectbox("Severity", SEVERITY_OPTIONS, index=2, key="incident_severity")
    with cols[1]:
        service = st.text_input("Service / Component", placeholder="Optional (e.g. auth-service)", key="incident_service")
    with cols[2]:
        analyze = st.button("🔍 ANALYZE INCIDENT", type="primary", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)
    return log, severity, service, analyze


def render_memory(similar: Any) -> None:
    st.markdown('<div class="panel-title">📚 MEMORY RECALL</div>', unsafe_allow_html=True)

    items = [normalize_memory_item(x) for x in extract_similar_list(similar)]
    if not items:
        st.info("No similar incidents found in memory.")
        return

    st.caption(f"{len(items)} similar incident(s) recalled from memory.")

    for index, item in enumerate(items[:6], start=1):
        outcome = item.get("outcome", "recorded").strip().lower()
        if outcome == "worked":
            badge = '<span class="badge-ok">✅ PREVIOUSLY WORKED</span>'
        elif outcome == "failed":
            badge = '<span class="badge-bad">❌ FAILED — AVOID THIS APPROACH</span>'
        else:
            badge = '<span class="badge-ok">HISTORICAL FACT</span>'

        log_snippet = item.get("log", "")[:280] or item.get("raw_text", "N/A")
        root = item.get("root_cause") or "N/A"
        fix = item.get("fix") or "N/A"

        with st.expander(f"Historical Incident #{index}", expanded=(index == 1)):
            st.markdown(badge, unsafe_allow_html=True)
            st.markdown(f"**Incident/Fact:** `{log_snippet}`")
            if root and root != "N/A":
                st.markdown(f"**Previous root cause:** {root}")
            if fix and fix != "N/A" and fix != log_snippet:
                st.markdown(f"**Previous fix:** {fix}")
            if outcome and outcome != "recorded":
                st.markdown(f"**Outcome:** `{outcome}`")


def render_ai_response(sections: dict[str, str]) -> None:
    st.markdown('<div class="panel-title">🤖 AI RESPONSE</div>', unsafe_allow_html=True)

    root = sections.get("root_cause", "").strip()
    fix = sections.get("recommended_fix", "").strip()
    precautions = sections.get("precautions", "").strip()
    raw = sections.get("raw", "").strip()

    if root or fix or precautions:
        if root:
            st.markdown(
                '<div class="response-card"><h4>🔍 LIKELY ROOT CAUSE</h4></div>',
                unsafe_allow_html=True,
            )
            st.markdown(root)
        if fix:
            st.markdown(
                '<div class="response-card"><h4>🛠️ RECOMMENDED FIX</h4></div>',
                unsafe_allow_html=True,
            )
            st.markdown(fix)
        if precautions:
            st.markdown(
                '<div class="response-card"><h4>🛡️ PRECAUTIONS &amp; PREVENTION</h4></div>',
                unsafe_allow_html=True,
            )
            st.markdown(precautions)
    else:
        st.markdown(
            '<div class="response-card"><h4>🤖 AI ANALYSIS &amp; RECOMMENDATION</h4></div>',
            unsafe_allow_html=True,
        )
        st.markdown(raw)


def render_feedback() -> None:
    st.markdown('<div class="panel"><div class="panel-title">WAS THIS FIX EFFECTIVE?</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        worked = st.button("✅ WORKED", use_container_width=True)
    with col2:
        failed = st.button("❌ FAILED", use_container_width=True)

    if worked:
        submit_feedback("worked")
    if failed:
        submit_feedback("failed")

    if st.session_state.feedback_message:
        css = "feedback-ok" if st.session_state.feedback_type == "success" else "feedback-bad"
        st.markdown(
            f'<div class="{css}">{st.session_state.feedback_message}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)


def submit_feedback(outcome: str) -> None:
    if not st.session_state.get("current_log") or not st.session_state.get("current_answer"):
        st.session_state.last_error = "No AI response available to save."
        return

    root_cause = st.session_state.get("current_root_cause") or "auto-detected"
    if not root_cause.strip():
        root_cause = "auto-detected"

    try:
        save_incident(
            st.session_state["current_log"],
            root_cause,
            st.session_state["current_answer"],
            outcome,
        )
        if outcome == "worked":
            st.session_state.feedback_message = "Saved! Agent will remember this fix worked."
            st.session_state.feedback_type = "success"
        else:
            st.session_state.feedback_message = (
                "Saved! Agent will avoid this fix next time."
            )
            st.session_state.feedback_type = "failed"
        st.session_state.last_error = None
    except Exception as exc:
        st.session_state.last_error = f"Memory save failed: {exc}"


def run_analysis(log: str) -> None:
    scan_slot = st.empty()
    pipe_slot = st.empty()
    similar: list[dict[str, Any]] = []
    sections: dict[str, str] | None = None

    try:
        step_index = 0
        for stage_label, action in ANALYSIS_STAGES:
            scan_slot.markdown(f'<div class="scan-box">{stage_label}</div>', unsafe_allow_html=True)
            step_index += 1
            with pipe_slot.container():
                render_pipeline(active_step=min(step_index, 4))

            if action == "memory":
                similar = find_similar(log)
            elif action == "groq":
                sections = analyze_with_groq(log, similar)

            time.sleep(0.35)

        scan_slot.empty()
        with pipe_slot.container():
            render_pipeline(active_step=4)

        recommended = (sections or {}).get("recommended_fix", "").strip()
        root = (sections or {}).get("root_cause", "").strip()

        st.session_state.current_log = log
        st.session_state.similar_incidents = similar
        st.session_state.ai_sections = sections
        st.session_state.current_answer = recommended if recommended else (sections or {}).get("raw", "")
        st.session_state.current_root_cause = root if root else "auto-detected"
        st.session_state.analysis_complete = True
        st.session_state.feedback_message = None
        st.session_state.feedback_type = None
        st.session_state.last_error = None
        st.session_state.last_warning = None

    except Exception as exc:
        st.session_state.last_error = str(exc)
        st.session_state.analysis_complete = bool(st.session_state.get("ai_sections"))
        scan_slot.empty()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title="Incident Command Center",
        page_icon="🚨",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_session_state()
    inject_global_styles()
    render_sidebar()

    header_col, core_col = st.columns([1.35, 0.65], gap="large")
    with header_col:
        render_header()
    with core_col:
        render_ai_core()

    if not get_groq_api_key():
        st.warning(
            "GROQ_API_KEY is not configured. Add your API key to the `.env` file to enable AI analysis."
        )

    log_input, _severity, _service, analyze_clicked = render_incident_input()

    if analyze_clicked:
        if not log_input.strip():
            st.session_state.last_warning = "Please paste an error log first."
            st.session_state.last_error = None
        elif not get_groq_api_key():
            st.session_state.last_error = (
                "Groq API key is not configured. Add GROQ_API_KEY to your .env file."
            )
            st.session_state.last_warning = None
        else:
            st.session_state.last_warning = None
            st.session_state.last_error = None
            run_analysis(log_input.strip())

    if st.session_state.last_warning:
        st.warning(st.session_state.last_warning)
    if st.session_state.last_error:
        st.error(st.session_state.last_error)

    if st.session_state.analysis_complete and st.session_state.ai_sections:
        st.markdown('<div class="panel"><div class="panel-title">INCIDENT PIPELINE</div>', unsafe_allow_html=True)
        render_pipeline(active_step=4)
        st.markdown("</div>", unsafe_allow_html=True)

        mem_col, ai_col = st.columns([1, 1], gap="large")
        with mem_col:
            st.markdown('<div class="panel">', unsafe_allow_html=True)
            render_memory(st.session_state.similar_incidents)
            st.markdown("</div>", unsafe_allow_html=True)
        with ai_col:
            st.markdown('<div class="panel">', unsafe_allow_html=True)
            render_ai_response(st.session_state.ai_sections)
            st.markdown("</div>", unsafe_allow_html=True)

        render_feedback()

    st.markdown('<div class="panel"><div class="panel-title">HOW THE AGENT WORKS</div>', unsafe_allow_html=True)
    render_architecture()
    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
