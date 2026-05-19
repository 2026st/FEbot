"""Tests for RAG embed query construction with conversation history."""

from febot.thread_session import ChatTurn, embed_query_text


def test_embed_query_without_history() -> None:
    assert embed_query_text("UDPとは", None) == "UDPとは"


def test_embed_query_with_prior_user_turn() -> None:
    history = [
        ChatTurn(role="user", text="TCPとは"),
        ChatTurn(role="assistant", text="TCPは…"),
    ]
    out = embed_query_text("UDPとの違いは？", history)
    assert "TCPとは" in out
    assert "UDPとの違いは？" in out
