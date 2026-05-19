"""Tests for RAG prompt building with conversation history."""

from febot.thread_session import ChatTurn, build_user_content_with_history


def test_build_rag_user_content_without_history() -> None:
    content = build_user_content_with_history(question="UDPとは", context="ctx")
    assert "【ユーザーの質問】" in content
    assert "UDPとは" in content
    assert "【参照抜粋】" in content
    assert "【これまでの会話】" not in content


def test_build_rag_user_content_with_history() -> None:
    history = [ChatTurn(role="user", text="TCPとは"), ChatTurn(role="assistant", text="…")]
    content = build_user_content_with_history(
        question="UDPとの違いは？", context="ctx", history=history
    )
    assert "【これまでの会話】" in content
    assert "TCPとは" in content
    assert "UDPとの違いは？" in content
