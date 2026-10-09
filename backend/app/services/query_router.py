"""
QueryRouter — deterministic pre-retrieval classifier.

Runs before any retrieval:
  1. Prompt-injection guard (highest priority, non-bypassable)
  2. Capability / meta questions (fast path, no RAG cost)
  3. Social / greeting messages (fast path, no RAG cost)
  4. Everything else goes to the RAG pipeline; the evidence gate decides
     whether the corpus can answer it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.services.fast_responses import (
    CAPABILITY_RESPONSE,
    INJECTION_RESPONSE,
    get_greeting_response,
)

CAT_GREETING = "greeting"
CAT_CAPABILITY = "capability"
CAT_INJECTION = "injection"
CAT_QUESTION = "question"

ROUTE_FAST = "fast_path"
ROUTE_RAG = "rag_pipeline"
ROUTE_DECLINE = "decline"


@dataclass
class RoutingDecision:
    category: str
    route: str
    confidence: float
    reason: str
    fast_response: Optional[str] = None


# Phrasings aimed at the assistant itself. Kept narrow so that ordinary
# questions ("how do enzymes act as catalysts?") are not flagged.
_INJECTION_PATTERNS = re.compile(
    r"""
    ignore\s+(?:all\s+|your\s+|any\s+|the\s+)?(?:previous\s+|prior\s+|above\s+|these\s+)?(?:instructions|rules|prompts?) |
    disregard\s+(?:all\s+|your\s+|the\s+)?(?:previous\s+|prior\s+|above\s+)?(?:instructions|rules|prompts?) |
    forget\s+(?:\w+\s+){0,3}(?:instructions|rules) |
    \b(?:act|behave)\s+as\s+(?:if\s+you\s+(?:are|were)|my\s+|an?\s+(?:ai|assistant|chatbot|unrestricted|unfiltered|evil|different|new)\b) |
    pretend\s+(?:you\s+are|to\s+be|that\s+you) |
    \byou\s+are\s+now\b |
    \bDAN\b |
    jailbreak |
    do\s+anything\s+now |
    new\s+persona |
    override\s+your\s+ |
    (?:reveal|print|show|repeat)\s+(?:your\s+|the\s+)?(?:system\s+prompt|hidden\s+instructions)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_GREETING_TOKENS = frozenset([
    "hi", "hello", "hey", "hiya", "howdy",
    "thanks", "thank", "ty", "thx", "cheers",
    "bye", "goodbye", "cya", "later", "see",
    "ok", "okay", "k", "sure", "yep", "yes", "no", "nope",
    "great", "nice", "cool", "perfect", "awesome", "good",
    "got", "much", "very", "noted", "understood", "alright", "right",
    "hmm", "wow", "morning", "evening", "afternoon",
])

_STOP = {"i", "a", "the", "to", "is", "it", "me", "my", "you", "your", "so", "that", "there"}

_CAPABILITY_RE = re.compile(
    "|".join([
        r"what can you (do|help|assist)",
        r"what do you (do|know|cover|support)",
        r"your capabilities",
        r"what (documents|books|pdfs|files|sources) do you",
        r"tell me about yourself",
        r"^\s*who are you",
        r"^\s*what are you\b",
        r"how (can|do) you help",
        r"what('s| is) your (purpose|function|role)",
    ]),
    re.IGNORECASE,
)


class QueryRouter:
    @staticmethod
    def classify(query: str, conversation_history=None) -> RoutingDecision:
        q = query.strip()

        if _INJECTION_PATTERNS.search(q):
            return RoutingDecision(CAT_INJECTION, ROUTE_DECLINE, 1.0,
                                   "Prompt injection attempt detected", INJECTION_RESPONSE)

        if _CAPABILITY_RE.search(q):
            return RoutingDecision(CAT_CAPABILITY, ROUTE_FAST, 0.95,
                                   "Capability question detected", CAPABILITY_RESPONSE)

        tokens = re.findall(r"[a-z']+", q.lower())
        if 0 < len(tokens) <= 5:
            meaningful = set(tokens) - _STOP
            if meaningful and meaningful.issubset(_GREETING_TOKENS):
                return RoutingDecision(CAT_GREETING, ROUTE_FAST, 0.92,
                                       "Social/greeting message detected", get_greeting_response(q))

        return RoutingDecision(CAT_QUESTION, ROUTE_RAG, 0.9,
                               "Content question; routed to retrieval with evidence gate")
