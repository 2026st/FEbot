"""Convert LLM Markdown output to Slack mrkdwn and Block Kit blocks."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from html import escape

log = logging.getLogger(__name__)

MAX_CONTEXT_ELEMENTS = 10

SLACK_OUTPUT_RULES = """
【Slack向け出力形式】
- 見出しは # または【見出し】（どちらも Block Kit の header に変換）
- 太字は *テキスト*（Slack形式）。** は使わない
- 箇条書きは行頭に - または •。順序付きは `1. 項目` 形式
- アンダーラインは __テキスト__（rich_text の underline。太字は * または **）
- 表は Markdown テーブルではなく箇条書き（例: - A: 出現5回）か ``` 内の固定幅テキスト
- 区切り線 --- は使わず、セクション間は空行
- ASCII図・コード・木構造は ``` で囲む
""".strip()

MAX_HEADER_LEN = 150
MAX_SECTION_LEN = 3000
MAX_BLOCKS = 50

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_HRULE_RE = re.compile(r"^(-{3,}|\*{3,}|_{3,})\s*$")
_TABLE_ROW_RE = re.compile(r"^\|.+\|$")
_TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BOLD_UNDER_RE = re.compile(r"__(.+?)__")
_SOURCES_HEADER_RE = re.compile(r"^【出典(?:URL)?】\s*$")
_SOURCES_ITEM_RE = re.compile(r"^[-*•]\s+(\S+)\s*$")
_BRACKET_HEADER_RE = re.compile(r"^【(.+)】\s*$")
_LIST_LINE_RE = re.compile(r"^[-*•]\s+(.+)$")
_ORDERED_LIST_LINE_RE = re.compile(r"^\d+\.\s+(.+)$")
_FULL_BOLD_LINE_RE = re.compile(r"^\*(.+)\*$")
_FULL_UNDERLINE_LINE_RE = re.compile(r"^__(.+)__$")
_INLINE_BOLD_RE = re.compile(r"\*([^*\n]+)\*")
_INLINE_UNDERLINE_RE = re.compile(r"__([^_\n]+)__")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
# Slack mrkdwn: closing * immediately before CJK / fullwidth breaks bold
_BOLD_BEFORE_NON_ASCII_RE = re.compile(r"(\*[^*\n]+\*)([\u0080-\uffff])")
_FULLWIDTH_COLON_AFTER_BOLD_RE = re.compile(r"(\*[^*\n]+\*)\uff1a")


class SegmentKind(str, Enum):
    HEADER = "header"
    DIVIDER = "divider"
    CODE = "code"
    TABLE = "table"
    TEXT = "text"


@dataclass
class Segment:
    kind: SegmentKind
    content: str
    level: int = 0  # heading level 1-6


def escape_mrkdwn(text: str) -> str:
    """Escape &, <, > for Slack mrkdwn (not inside code fences)."""
    return escape(text, quote=False)


def fix_slack_mrkdwn(text: str) -> str:
    """Fix mrkdwn patterns that Slack fails to render (esp. after Japanese text)."""
    text = _BOLD_RE.sub(r"*\1*", text)
    text = _BOLD_UNDER_RE.sub(r"*\1*", text)
    text = _FULLWIDTH_COLON_AFTER_BOLD_RE.sub(r"\1: ", text)
    text = _BOLD_BEFORE_NON_ASCII_RE.sub(r"\1 \2", text)
    return text


def _normalize_list_line(line: str) -> str:
    """Use bullet char; mrkdwn section blocks do not render '- ' as a list."""
    stripped = line.strip()
    m = _LIST_LINE_RE.match(stripped)
    if m:
        return f"• {_convert_inline_markdown(m.group(1))}"
    om = _ORDERED_LIST_LINE_RE.match(stripped)
    if om:
        num = stripped.split(".", 1)[0]
        return f"{num}. {_convert_inline_markdown(om.group(1))}"
    return _convert_inline_markdown(line)


def _convert_inline_markdown(line: str) -> str:
    """Convert inline Markdown to Slack mrkdwn on a single line."""
    line = _LINK_RE.sub(r"<\2|\1>", line)
    line = _BOLD_RE.sub(r"*\1*", line)
    line = _BOLD_UNDER_RE.sub(r"*\1*", line)
    if "<" not in line:
        line = escape_mrkdwn(line)
    return line


def markdown_to_mrkdwn(text: str) -> str:
    """Convert Markdown body to a single Slack mrkdwn string (no Block Kit)."""
    body, _sources = split_sources_section(text)
    lines = body.splitlines()
    out: list[str] = []
    in_code = False
    table_buf: list[str] = []

    def flush_table() -> None:
        nonlocal table_buf
        if table_buf:
            out.append("```")
            out.extend(table_buf)
            out.append("```")
            table_buf = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_table()
            in_code = not in_code
            out.append(line)
            continue
        if in_code:
            out.append(line)
            continue
        if _TABLE_ROW_RE.match(stripped) or (_TABLE_SEP_RE.match(stripped) and table_buf):
            table_buf.append(line.rstrip())
            continue
        flush_table()
        if _HRULE_RE.match(stripped):
            out.append("─────────")
            continue
        m = _HEADING_RE.match(line)
        if m:
            title = m.group(2).strip()
            out.append(f"*{escape_mrkdwn(_convert_inline_markdown(title))}*")
            continue
        out.append(_normalize_list_line(line))
    flush_table()
    result = fix_slack_mrkdwn("\n".join(out).strip())
    if _sources:
        result += "\n\n*出典*\n" + "\n".join(f"• <{u}>" for u in _sources)
    return result


def split_sources_section(text: str) -> tuple[str, list[str]]:
    """Split trailing 【出典】 / 【出典URL】 section from body."""
    lines = text.splitlines()
    sources_start: int | None = None
    for i, line in enumerate(lines):
        if _SOURCES_HEADER_RE.match(line.strip()):
            sources_start = i
            break
    if sources_start is None:
        return text.strip(), []

    body = "\n".join(lines[:sources_start]).strip()
    sources: list[str] = []
    for line in lines[sources_start + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        m = _SOURCES_ITEM_RE.match(stripped)
        if m:
            url = m.group(1)
            if url not in sources:
                sources.append(url)
        elif stripped.startswith("http"):
            if stripped not in sources:
                sources.append(stripped)
    return body, sources


def _parse_segments(body: str) -> list[Segment]:
    lines = body.splitlines()
    segments: list[Segment] = []
    text_buf: list[str] = []
    table_buf: list[str] = []
    code_buf: list[str] = []
    in_code = False

    def flush_text() -> None:
        nonlocal text_buf
        if text_buf:
            joined = "\n".join(text_buf).strip()
            if joined:
                segments.append(Segment(SegmentKind.TEXT, joined))
            text_buf = []

    def flush_table() -> None:
        nonlocal table_buf
        if table_buf:
            segments.append(Segment(SegmentKind.TABLE, "\n".join(table_buf)))
            table_buf = []

    def flush_code() -> None:
        nonlocal code_buf
        if code_buf:
            segments.append(Segment(SegmentKind.CODE, "\n".join(code_buf)))
            code_buf = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_table()
            flush_text()
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_buf.append(line)
            continue

        if _TABLE_ROW_RE.match(stripped) or (_TABLE_SEP_RE.match(stripped) and table_buf):
            flush_text()
            table_buf.append(line.rstrip())
            continue
        flush_table()

        if _HRULE_RE.match(stripped):
            flush_text()
            segments.append(Segment(SegmentKind.DIVIDER, ""))
            continue

        m = _HEADING_RE.match(line)
        if m:
            flush_text()
            level = len(m.group(1))
            segments.append(Segment(SegmentKind.HEADER, m.group(2).strip(), level=level))
            continue

        bm = _BRACKET_HEADER_RE.match(stripped)
        if bm and not _SOURCES_HEADER_RE.match(stripped):
            flush_text()
            segments.append(Segment(SegmentKind.HEADER, bm.group(1).strip()))
            continue

        text_buf.append(line)

    flush_table()
    flush_text()
    if in_code:
        flush_code()
    return segments


def _segment_to_mrkdwn(segment: Segment) -> str:
    if segment.kind == SegmentKind.CODE:
        return f"```{segment.content}```"
    if segment.kind == SegmentKind.TABLE:
        return f"```\n{segment.content}\n```"
    if segment.kind == SegmentKind.TEXT:
        lines = [_normalize_list_line(ln) for ln in segment.content.splitlines()]
        return fix_slack_mrkdwn("\n".join(lines))
    return ""


def _rich_text_element(
    text: str,
    *,
    bold: bool = False,
    code: bool = False,
    underline: bool = False,
) -> dict:
    el: dict = {"type": "text", "text": text}
    style: dict[str, bool] = {}
    if bold:
        style["bold"] = True
    if code:
        style["code"] = True
    if underline:
        style["underline"] = True
    if style:
        el["style"] = style
    return el


def _rich_text_link(url: str, label: str) -> dict:
    return {"type": "link", "url": url, "text": label}


def _parse_inline_to_rich_elements(text: str) -> list[dict]:
    """Parse inline *bold*, __underline__, `code`, [label](url) into rich_text elements."""
    text = _BOLD_RE.sub(r"*\1*", text)
    patterns: list[tuple[str, re.Pattern[str]]] = [
        ("link", _LINK_RE),
        ("code", _INLINE_CODE_RE),
        ("underline", _INLINE_UNDERLINE_RE),
        ("bold", _INLINE_BOLD_RE),
    ]
    elements: list[dict] = []
    pos = 0
    while pos < len(text):
        best: re.Match[str] | None = None
        best_kind = ""
        for kind, pat in patterns:
            m = pat.search(text, pos)
            if m and (best is None or m.start() < best.start()):
                best = m
                best_kind = kind
        if best is None:
            tail = text[pos:]
            if tail:
                elements.append(_rich_text_element(tail))
            break
        if best.start() > pos:
            elements.append(_rich_text_element(text[pos : best.start()]))
        if best_kind == "link":
            elements.append(_rich_text_link(best.group(2), best.group(1)))
        elif best_kind == "code":
            elements.append(_rich_text_element(best.group(1), code=True))
        elif best_kind == "underline":
            elements.append(_rich_text_element(best.group(1), underline=True))
        else:
            elements.append(_rich_text_element(best.group(1), bold=True))
        pos = best.end()
    return elements


def _rich_text_section(elements: list[dict]) -> dict:
    return {"type": "rich_text_section", "elements": elements}


def _rich_text_list_block(items: list[str], *, style: str = "bullet") -> dict:
    return {
        "type": "rich_text_list",
        "style": style,
        "elements": [_rich_text_section(_parse_inline_to_rich_elements(item)) for item in items],
    }


def _line_to_rich_elements(line: str) -> list[dict]:
    """Parse one line into rich_text elements (bold/code/link; not mrkdwn)."""
    stripped = line.strip()
    if not stripped:
        return []
    m = _FULL_BOLD_LINE_RE.match(stripped)
    if m:
        return [_rich_text_element(m.group(1), bold=True)]
    um = _FULL_UNDERLINE_LINE_RE.match(stripped)
    if um:
        return [_rich_text_element(um.group(1), underline=True)]
    return _parse_inline_to_rich_elements(stripped)


def _text_segment_needs_rich_text(content: str) -> bool:
    for line in content.splitlines():
        s = line.strip()
        if not s:
            continue
        if (
            _LIST_LINE_RE.match(s)
            or _ORDERED_LIST_LINE_RE.match(s)
            or _FULL_BOLD_LINE_RE.match(s)
            or _FULL_UNDERLINE_LINE_RE.match(s)
            or _INLINE_BOLD_RE.search(s)
            or _INLINE_UNDERLINE_RE.search(s)
            or _INLINE_CODE_RE.search(s)
        ):
            return True
    return False


def _text_segment_to_blocks(content: str) -> list[dict]:
    """Use rich_text blocks for lists / bold (mrkdwn section is unreliable for these)."""
    elements: list[dict] = []
    list_buf: list[str] = []
    list_style: str | None = None

    def flush_list() -> None:
        nonlocal list_buf, list_style
        if list_buf and list_style:
            elements.append(_rich_text_list_block(list_buf, style=list_style))
        list_buf = []
        list_style = None

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            flush_list()
            continue
        om = _ORDERED_LIST_LINE_RE.match(stripped)
        if om:
            if list_style == "bullet":
                flush_list()
            if list_style is None:
                list_style = "ordered"
            list_buf.append(om.group(1))
            continue
        lm = _LIST_LINE_RE.match(stripped)
        if lm:
            if list_style == "ordered":
                flush_list()
            if list_style is None:
                list_style = "bullet"
            list_buf.append(lm.group(1))
            continue
        flush_list()
        line_els = _line_to_rich_elements(line)
        if line_els:
            elements.append(_rich_text_section(line_els))

    flush_list()
    if not elements:
        return []
    return [{"type": "rich_text", "elements": elements}]


def _segment_to_blocks(segment: Segment) -> list[dict]:
    if segment.kind == SegmentKind.CODE:
        return [_section_block(f"```{segment.content}```")]
    if segment.kind == SegmentKind.TABLE:
        return [_section_block(f"```\n{segment.content}\n```")]
    if segment.kind == SegmentKind.TEXT:
        if _text_segment_needs_rich_text(segment.content):
            return _text_segment_to_blocks(segment.content)
        mrkdwn = _segment_to_mrkdwn(segment)
        if not mrkdwn.strip():
            return []
        return [_section_block(chunk) for chunk in _split_mrkdwn_chunks(mrkdwn)]
    return []


def _split_mrkdwn_chunks(text: str, max_len: int = MAX_SECTION_LEN) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, max_len)
        if split_at <= 0:
            split_at = max_len
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip("\n")
    return chunks


def _header_block(title: str) -> dict:
    plain = title[:MAX_HEADER_LEN]
    return {
        "type": "header",
        "text": {"type": "plain_text", "text": plain, "emoji": True},
    }


def _section_block(mrkdwn: str) -> dict:
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": mrkdwn[:MAX_SECTION_LEN]},
    }


def _context_blocks(sources: list[str]) -> list[dict]:
    """Build context block(s) for sources. Slack allows max 10 elements per context block."""
    blocks: list[dict] = []
    remaining = list(sources)
    first = True
    while remaining:
        elements: list[dict] = []
        budget = MAX_CONTEXT_ELEMENTS - (1 if first else 0)
        if first:
            elements.append({"type": "mrkdwn", "text": "*出典*"})
            first = False
        for url in remaining[:budget]:
            elements.append({"type": "mrkdwn", "text": f"<{url}>"})
        remaining = remaining[budget:]
        blocks.append({"type": "context", "elements": elements})
    return blocks


def build_slack_blocks(
    body: str,
    *,
    footer: str | None = None,
    sources: list[str] | None = None,
) -> tuple[str, list[dict]]:
    """Build (fallback_text, blocks) for chat.postMessage."""
    main_body, embedded_sources = split_sources_section(body)
    all_sources = list(sources or [])
    for url in embedded_sources:
        if url not in all_sources:
            all_sources.append(url)

    segments = _parse_segments(main_body)
    blocks: list[dict] = []

    for seg in segments:
        if seg.kind == SegmentKind.HEADER:
            blocks.append(_header_block(seg.content))
        elif seg.kind == SegmentKind.DIVIDER:
            blocks.append({"type": "divider"})
        else:
            blocks.extend(_segment_to_blocks(seg))

    if all_sources:
        blocks.extend(_context_blocks(all_sources))

    if footer:
        blocks.append(_section_block(footer))

    if len(blocks) > MAX_BLOCKS:
        log.warning("Slack blocks exceed %d; falling back to plain mrkdwn", MAX_BLOCKS)
        fallback = markdown_to_mrkdwn(body)
        if footer:
            fallback = f"{fallback}\n\n{footer}"
        return fallback[:4000], []

    fallback_parts: list[str] = []
    for seg in segments:
        if seg.kind == SegmentKind.HEADER:
            fallback_parts.append(f"*{seg.content}*")
        elif seg.kind == SegmentKind.DIVIDER:
            fallback_parts.append("─────────")
        else:
            part = _segment_to_mrkdwn(seg)
            if part:
                fallback_parts.append(part)
    fallback = "\n\n".join(fallback_parts).strip() or markdown_to_mrkdwn(body)
    if all_sources:
        fallback += "\n\n出典: " + ", ".join(all_sources[:3])
        if len(all_sources) > 3:
            fallback += " …"
    if footer:
        fallback = f"{fallback}\n\n{footer}"

    return fallback[:4000], blocks


FORMAT_TEST_FOOTER = "_（Slack 表示テスト。AI・RAG は使用していません）_"
FORMAT_TEST_KEYWORDS = ("フォーマットテスト", "表示テスト")


def format_test_sample_body() -> str:
    """Sample RAG-style answer for manual Slack layout checks (no LLM)."""
    return (
        "【量子鍵配送とは】\n"
        "*量子力学の性質を使って、盗聴されない安全な「暗号の鍵」を相手と共有する技術*\n\n"
        "【量子鍵配送の特徴】\n"
        "- 使う技術: 量子力学の原理\n"
        "- 目的: ランダムな鍵を安全に共有する\n"
        "- 最大の特徴: 盗聴されたら必ずバレる\n\n"
        "【代表的な方式】\n"
        "- BB84方式: 最も有名な量子鍵配送プロトコル\n\n"
        "通常の本文です。`インラインコード` と __アンダーライン__ の例。\n\n"
        "【手順】\n"
        "1. 鍵を生成する\n"
        "2. 量子チャネルで送る\n\n"
        "|方式|備考|\n"
        "|---|---|\n"
        "|BB84|標準|\n\n"
        "【出典】\n"
        "- https://www.ipa.go.jp/\n"
    )


def wants_format_test(text: str) -> bool:
    return text.strip() in FORMAT_TEST_KEYWORDS


def format_reply_for_history(
    body: str,
    *,
    sources: list[str] | None = None,
    footer: str | None = None,
) -> str:
    """Plain mrkdwn string for thread session storage."""
    text = markdown_to_mrkdwn(body)
    extra_sources = sources or []
    embedded = split_sources_section(body)[1]
    for url in extra_sources:
        if url not in embedded:
            embedded.append(url)
    if embedded and "出典" not in text:
        text += "\n\n*出典*\n" + "\n".join(f"• <{u}>" for u in embedded)
    if footer:
        text = f"{text}\n\n{footer}"
    return text
