import re
from typing import List

from app.models.schemas import ConversationTurn

MAX_HISTORY_TURNS = 6     # hard cap (3 user + 3 assistant)
MAX_HISTORY_TOKENS = 800  # soft cap after hard cap

_FOLLOWUP_RE = re.compile(
    r"\b(it|its|it's|this|that|these|those|they|them|their|he|she|his|her|the same|above|previous|former|latter)\b"
    r"|^(and|but|so|also|what about|how about|why|explain|elaborate|more)\b",
    re.IGNORECASE,
)


def trim_history(history: List[ConversationTurn]) -> List[ConversationTurn]:
    """Trims the conversation history to fit within turn and token limits."""
    if not history:
        return []
    history = history[-MAX_HISTORY_TURNS:]
    while _estimate_tokens(history) > MAX_HISTORY_TOKENS and len(history) > 2:
        history = history[1:]
    return history


def _estimate_tokens(history: List[ConversationTurn]) -> int:
    """Fast estimate: words * 1.3."""
    if not history:
        return 0
    return int(sum(len(t.content.split()) for t in history) * 1.3)


def needs_rewrite(query: str, history: List[ConversationTurn]) -> bool:
    """A query needs rewriting only when there is history and it looks like a follow-up."""
    if not history:
        return False
    return len(query.split()) <= 6 or bool(_FOLLOWUP_RE.search(query))


def build_effective_query(query: str, history: List[ConversationTurn]) -> str:
    """Heuristic rewrite (fallback when the LLM rewrite is unavailable): append the last
    user question so pronouns in a follow-up have something to resolve against."""
    if not needs_rewrite(query, history):
        return query
    last_user = next((t.content for t in reversed(history) if t.role == "user"), "")
    return f"{query} {last_user[:300]}".strip() if last_user else query
