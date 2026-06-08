"""Tests for Slack mrkdwn / Block Kit formatting."""

from febot.slack_format import (
    build_slack_blocks,
    fix_slack_mrkdwn,
    format_test_sample_body,
    markdown_to_mrkdwn,
    split_sources_section,
    wants_format_test,
)


def test_bold_conversion() -> None:
    assert "*ハフマン*" in markdown_to_mrkdwn("**ハフマン**は圧縮方式です。")


def test_heading_becomes_bold_line() -> None:
    out = markdown_to_mrkdwn("## 簡単に言うと\n本文です。")
    assert "*簡単に言うと*" in out
    assert "##" not in out


def test_build_slack_blocks_header() -> None:
    body = "## 簡単に言うと\n\n**ハフマン符号化**の説明。"
    _fallback, blocks = build_slack_blocks(body)
    headers = [b for b in blocks if b.get("type") == "header"]
    assert len(headers) == 1
    assert headers[0]["text"]["text"] == "簡単に言うと"


def test_table_becomes_code_block() -> None:
    body = "|文字|回数|\n|---|---|\n|A|5|\n|B|3|"
    _fallback, blocks = build_slack_blocks(body)
    sections = [b for b in blocks if b.get("type") == "section"]
    assert any("```" in b["text"]["text"] for b in sections)


def test_sources_split_and_context_block() -> None:
    body = "回答本文\n\n【出典】\n- https://example.com/a\n- https://example.com/b"
    main, urls = split_sources_section(body)
    assert "【出典】" not in main
    assert len(urls) == 2
    _fallback, blocks = build_slack_blocks(body)
    assert any(b.get("type") == "context" for b in blocks)


def test_sources_passed_explicitly() -> None:
    _fallback, blocks = build_slack_blocks("本文", sources=["https://example.com"])
    contexts = [b for b in blocks if b.get("type") == "context"]
    assert len(contexts) == 1
    assert "https://example.com" in contexts[0]["elements"][1]["text"]


def test_many_sources_respect_context_element_limit() -> None:
    urls = [f"https://example.com/{i}" for i in range(10)]
    _fallback, blocks = build_slack_blocks("本文", sources=urls)
    contexts = [b for b in blocks if b.get("type") == "context"]
    assert len(contexts) == 2
    assert len(contexts[0]["elements"]) == 10
    assert contexts[0]["elements"][0]["text"] == "*出典*"
    assert len(contexts[1]["elements"]) == 1


def test_long_section_split() -> None:
    body = "x" * 3500
    _fallback, blocks = build_slack_blocks(body)
    sections = [b for b in blocks if b.get("type") == "section"]
    assert len(sections) >= 2
    for sec in sections:
        assert len(sec["text"]["text"]) <= 3000


def test_escape_ampersand_in_plain_text() -> None:
    out = markdown_to_mrkdwn("A & B は演算子です。")
    assert "&amp;" in out


def test_link_conversion() -> None:
    out = markdown_to_mrkdwn("[IPA](https://www.ipa.go.jp/)")
    assert "<https://www.ipa.go.jp/|IPA>" in out


def test_footer_section() -> None:
    _fallback, blocks = build_slack_blocks("本文", footer="_注記_")
    assert blocks[-1]["type"] == "section"
    assert blocks[-1]["text"]["text"] == "_注記_"


def test_bracket_header_becomes_header_block() -> None:
    body = "【量子鍵配送とは】\n\n本文です。"
    _fallback, blocks = build_slack_blocks(body)
    headers = [b for b in blocks if b.get("type") == "header"]
    assert len(headers) == 1
    assert headers[0]["text"]["text"] == "量子鍵配送とは"


def test_list_uses_rich_text_list() -> None:
    body = "【特徴】\n- 項目A\n- 項目B"
    _fallback, blocks = build_slack_blocks(body)
    rich = [b for b in blocks if b.get("type") == "rich_text"]
    assert len(rich) == 1
    lists = [e for e in rich[0]["elements"] if e.get("type") == "rich_text_list"]
    assert len(lists) == 1
    assert lists[0]["elements"][0]["elements"][0]["text"] == "項目A"


def test_full_line_bold_uses_rich_text_bold_style() -> None:
    body = "*量子力学の性質を使う技術*\n通常の行"
    _fallback, blocks = build_slack_blocks(body)
    rich = blocks[0]
    assert rich["type"] == "rich_text"
    first = rich["elements"][0]["elements"][0]
    assert first["style"]["bold"] is True
    assert "量子力学" in first["text"]


def test_fix_slack_mrkdwn_inserts_space_before_cjk() -> None:
    out = fix_slack_mrkdwn("*重要*です")
    assert out == "*重要* です"


def test_markdown_list_uses_bullet_char() -> None:
    out = markdown_to_mrkdwn("- 使う技術: 量子力学")
    assert out.startswith("• ")


def test_format_test_sample_uses_header_and_rich_text() -> None:
    _fallback, blocks = build_slack_blocks(format_test_sample_body())
    assert any(b.get("type") == "header" for b in blocks)
    assert any(b.get("type") == "rich_text" for b in blocks)
    assert any(b.get("type") == "context" for b in blocks)


def test_inline_code_uses_rich_text_code_style() -> None:
    body = "【特徴】\n- 項目A\n\n通常。`インラインコード` です。"
    _fallback, blocks = build_slack_blocks(body)
    rich = next(b for b in blocks if b.get("type") == "rich_text")
    found_code = False
    for block_el in rich["elements"]:
        if block_el.get("type") != "rich_text_section":
            continue
        for el in block_el["elements"]:
            if el.get("style", {}).get("code") and "インラインコード" in el.get("text", ""):
                found_code = True
    assert found_code


def test_inline_code_only_body_uses_rich_text_code_style() -> None:
    body = "通常の本文です。`インラインコード` の例。"
    _fallback, blocks = build_slack_blocks(body)
    rich = next(b for b in blocks if b.get("type") == "rich_text")
    code_els = [
        el
        for sec in rich["elements"]
        if sec.get("type") == "rich_text_section"
        for el in sec["elements"]
        if el.get("style", {}).get("code")
    ]
    assert any("インラインコード" in el["text"] for el in code_els)


def _rich_text_lists(blocks: list[dict], *, style: str | None = None) -> list[dict]:
    out: list[dict] = []
    for block in blocks:
        if block.get("type") != "rich_text":
            continue
        for el in block["elements"]:
            if el.get("type") != "rich_text_list":
                continue
            if style is None or el.get("style") == style:
                out.append(el)
    return out


def _rich_text_underline_texts(blocks: list[dict]) -> list[str]:
    texts: list[str] = []
    for block in blocks:
        if block.get("type") != "rich_text":
            continue
        for container in block["elements"]:
            if container.get("type") not in ("rich_text_section", "rich_text_list"):
                continue
            sections = (
                [container]
                if container.get("type") == "rich_text_section"
                else container.get("elements", [])
            )
            for sec in sections:
                for el in sec.get("elements", []):
                    if el.get("style", {}).get("underline"):
                        texts.append(el["text"])
    return texts


def test_ordered_list_uses_rich_text_ordered_style() -> None:
    body = "【手順】\n1. 鍵を生成する\n2. 量子チャネルで送る"
    _fallback, blocks = build_slack_blocks(body)
    ordered = _rich_text_lists(blocks, style="ordered")
    assert len(ordered) == 1
    items = [sec["elements"][0]["text"] for sec in ordered[0]["elements"]]
    assert items == ["鍵を生成する", "量子チャネルで送る"]


def test_underline_inline_uses_rich_text_underline_style() -> None:
    body = "本文 __アンダーライン__ です。"
    _fallback, blocks = build_slack_blocks(body)
    assert "アンダーライン" in _rich_text_underline_texts(blocks)


def test_full_line_underline_uses_rich_text_underline_style() -> None:
    body = "__行全体の下線__"
    _fallback, blocks = build_slack_blocks(body)
    assert _rich_text_underline_texts(blocks) == ["行全体の下線"]


def test_format_test_sample_includes_ordered_list_and_underline() -> None:
    _fallback, blocks = build_slack_blocks(format_test_sample_body())
    assert _rich_text_lists(blocks, style="ordered")
    assert "アンダーライン" in _rich_text_underline_texts(blocks)


def test_wants_format_test_keywords() -> None:
    assert wants_format_test("フォーマットテスト") is True
    assert wants_format_test("表示テスト") is True
    assert wants_format_test("量子鍵配送") is False
