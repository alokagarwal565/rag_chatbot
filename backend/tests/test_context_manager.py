from app.models.schemas import ConversationTurn
from app.services.context_manager import build_effective_query, needs_rewrite, trim_history


def test_trim_history_empty():
    assert trim_history([]) == []


def test_trim_history_over_turn_limit():
    history = [ConversationTurn(role="user" if i % 2 == 0 else "assistant", content=f"msg {i}") for i in range(8)]
    trimmed = trim_history(history)
    assert len(trimmed) == 6
    assert trimmed[0].content == "msg 2"


def test_trim_history_keeps_last_exchange_over_token_limit():
    history = [ConversationTurn(role="user", content="a " * 500),
               ConversationTurn(role="assistant", content="b " * 500)]
    assert len(trim_history(history)) == 2


def test_needs_rewrite_only_for_followups():
    history = [ConversationTurn(role="user", content="What is osmosis?"),
               ConversationTurn(role="assistant", content="Osmosis is diffusion of water across a membrane [1].")]
    assert needs_rewrite("Why does it matter for cells?", history)
    assert not needs_rewrite("Why does it matter for cells?", [])
    assert not needs_rewrite("Describe the structure of the mitochondrial inner membrane in eukaryotes", history)


def test_heuristic_effective_query_appends_last_user_question():
    history = [ConversationTurn(role="user", content="What is osmosis?"),
               ConversationTurn(role="assistant", content="Osmosis is ...")]
    assert build_effective_query("Why does it happen?", history) == "Why does it happen? What is osmosis?"
