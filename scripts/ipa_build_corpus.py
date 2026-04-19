#!/usr/bin/env python3
"""Fetch IPA PDFs (optional) and emit Markdown corpus files for RAG ingest."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

import yaml
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "ipa_manifest.yaml"
RAW_DIR = ROOT / "data" / "ipa_raw"
CORPUS_DIR = ROOT / "data" / "corpus"

KIND_TITLE = {
    "past_questions": "過去問題（問題冊子・抜粋）",
    "answers": "解答例",
    "commentary": "採点講評",
    "syllabus": "基本情報技術者試験シラバス（試験の範囲）",
}


def _safe_pdf_name(url: str) -> str:
    path = unquote(urlparse(url).path)
    name = Path(path).name
    if not name.lower().endswith(".pdf"):
        raise ValueError(f"URL does not end with .pdf: {url}")
    return re.sub(r"[^a-zA-Z0-9._-]", "_", name)


def _fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(
        url,
        headers={"User-Agent": "FEbot-ipa_build_corpus/1.0"},
    )
    with urlopen(req, timeout=120) as resp:
        data = resp.read()
    dest.write_bytes(data)


def _extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        t = page.extract_text() or ""
        parts.append(f"\n\n<!-- page {i + 1} -->\n\n{t}")
    return "".join(parts).strip()


def _header(
    *, title: str, pdf_url: str, source_page: str, faq_url: str, past_top: str, generated_at: str
) -> str:
    return f"""# {title}

> 本ファイルは IPA が公表した PDF から **機械的に抽出したテキスト** です。レイアウト・図表・数式は欠落や順序崩れがある場合があります。試験の正式な内容・解答・採点の解釈は **必ず公式 PDF** で確認してください。
>
> - **出典 PDF**: {pdf_url}
> - **公式一覧ページ**: {source_page}
> - **過去問題トップ**: {past_top}
> - **IPA 過去問題の留意点（FAQ）**: {faq_url}
> - **テキスト抽出日時（UTC）**: {generated_at}

---
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ipa-*.md corpus from IPA PDFs.")
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Download PDFs into data/ipa_raw/ before extraction (requires network).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST,
        help="Path to ipa_manifest.yaml",
    )
    args = parser.parse_args()

    if not args.manifest.is_file():
        raise SystemExit(f"Manifest not found: {args.manifest}")

    data = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    faq_url = data.get("ipa_notice_faq", "https://www.ipa.go.jp/shiken/faq.html#seido")
    past_top = data.get("ipa_past_top", "https://www.ipa.go.jp/shiken/mondai-kaiotu/index.html")

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        url = entry["url"]
        source_page = entry.get("source_page") or past_top
        stem = entry["output_stem"]
        kind = entry.get("doc_kind", "past_questions")
        title = KIND_TITLE.get(kind, "IPA 公表資料")

        pdf_name = _safe_pdf_name(url)
        pdf_path = RAW_DIR / pdf_name

        if args.fetch:
            print(f"fetch {url}")
            _fetch(url, pdf_path)
        elif not pdf_path.is_file():
            raise SystemExit(
                f"Missing PDF {pdf_path}. Run with --fetch or place the file there.\n  URL: {url}"
            )

        print(f"extract -> {stem}.md")
        body = _extract_text(pdf_path)
        head = _header(
            title=title,
            pdf_url=url,
            source_page=source_page,
            faq_url=faq_url,
            past_top=past_top,
            generated_at=generated_at,
        )
        out = CORPUS_DIR / f"{stem}.md"
        out.write_text(head + "\n\n" + body + "\n", encoding="utf-8")

    print(f"Wrote {len(entries)} files under {CORPUS_DIR}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
