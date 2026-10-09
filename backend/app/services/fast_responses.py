"""
Pre-computed fast-path responses for non-RAG query categories.
These are returned instantly without touching the retrieval pipeline.
"""
import random

CAPABILITY_RESPONSE = (
    "I'm **Granth**, an open-source PDF knowledge assistant. Here's what I can do:\n\n"
    "- Answer questions using only the PDFs indexed in this library\n"
    "- Cite every answer with the source file and page number\n"
    "- Show the exact page image and the passage I used\n"
    "- Read scanned pages too (they are OCR'd during ingestion)\n\n"
    "If the indexed documents don't contain the answer, I'll say so instead of guessing."
)

GREETING_RESPONSES = [
    "Hello! Ask me anything about the documents in the library.",
    "Hi there! What would you like to look up in the indexed PDFs?",
    "Hey! Ask a question and I'll answer it with page-level citations.",
]

THANKS_RESPONSES = [
    "You're welcome! Ask another question any time.",
    "Happy to help! Anything else you'd like to look up?",
]

FAREWELL_RESPONSES = [
    "Goodbye! Come back any time.",
    "See you! The library will be here.",
]

INJECTION_RESPONSE = (
    "I can only answer questions from the indexed documents, and I can't change my instructions. "
    "Ask me something about the library's content."
)


def get_greeting_response(text: str) -> str:
    """Pick an appropriate greeting response based on input."""
    t = text.lower().strip().rstrip("!.,")
    if any(w in t for w in ("thank", "thanks", "thx", "ty")):
        return random.choice(THANKS_RESPONSES)
    if any(w in t for w in ("bye", "goodbye", "see you", "cya", "later")):
        return random.choice(FAREWELL_RESPONSES)
    return random.choice(GREETING_RESPONSES)
