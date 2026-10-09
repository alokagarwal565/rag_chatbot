"""LLM judge: splits an answer into claims and checks each against the numbered sources it was given."""
import json
from typing import List

JUDGE_SYSTEM = """You are a strict fact-checking judge for a retrieval-augmented QA system.
You get a question, an answer containing citation markers like [2], and the numbered sources the answer
was generated from. Split the answer into atomic factual claims. For each claim decide whether it is
supported by ANY of the sources (supported_by_any), and list the source numbers it cites.
Then, for every source number cited anywhere in the answer, decide whether that source supports at
least one of the claims that cite it (supports).
Judge only against the sources, never against your own knowledge. Paraphrase is fine; added facts,
numbers, or conclusions not in the sources are unsupported.
Return JSON only:
{"claims": [{"claim": "...", "cited": [1], "supported_by_any": true}],
 "sources": [{"n": 1, "supports": true}]}"""


async def judge_answer(llm, question: str, answer: str, context: List[dict]) -> dict:
    sources = "\n\n".join(f"[{c['context_n']}] ({c['filename']}, {c['page_label']})\n{c['text']}"
                          for c in sorted(context, key=lambda c: c["context_n"]))
    prompt = f"QUESTION:\n{question}\n\nANSWER:\n{answer}\n\nSOURCES:\n{sources}"
    try:
        res = await llm.generate(prompt, JUDGE_SYSTEM, tier="heavy", max_tokens=2000, json_mode=True, timeout=60)
    except Exception:  # noqa: BLE001 - heavy tier out of quota / overloaded: judge with the fast tier
        res = await llm.generate(prompt, JUDGE_SYSTEM, tier="fast", max_tokens=2000, json_mode=True, timeout=60)
    data = json.loads(res.text)
    claims = data.get("claims", [])
    return {
        "claims": claims,
        "sources": data.get("sources", []),
        "n_claims": len(claims),
        "n_unsupported": sum(1 for c in claims if not c.get("supported_by_any")),
        "model": res.model,
    }
