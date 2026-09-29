"""
Persistent incident memory using Hindsight for the Incident Response Agent.

Fixed interface:
    save_incident(log, root_cause, fix, outcome)
    find_similar(new_log)
"""

from __future__ import annotations

from pathlib import Path
import os
from dotenv import load_dotenv
from hindsight_client import Hindsight

ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_FILE, override=True)

BANK_ID = "incident-response"  # must match exactly what you named it on the dashboard


def get_hindsight_client() -> Hindsight:
    load_dotenv(dotenv_path=ENV_FILE, override=True)
    return Hindsight(
        base_url="https://api.hindsight.vectorize.io",
        api_key=os.getenv("HINDSIGHT_API_KEY")
    )


def save_incident(log: str, root_cause: str, fix: str, outcome: str):
    """
    Save an incident and its resolution outcome to Hindsight memory bank.
    """
    text = f"Error: {log}\nRoot cause: {root_cause}\nFix: {fix}\nOutcome: {outcome}"
    client = get_hindsight_client()
    return client.retain(bank_id=BANK_ID, content=text)


def find_similar(new_log: str):
    """
    Recall similar past incidents from Hindsight memory bank.
    """
    client = get_hindsight_client()
    return client.recall(bank_id=BANK_ID, query=new_log)


def memory_is_available() -> bool:
    """Check if Hindsight memory service is configured."""
    load_dotenv(dotenv_path=ENV_FILE, override=True)
    return bool(os.getenv("HINDSIGHT_API_KEY"))

