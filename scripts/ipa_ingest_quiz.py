#!/usr/bin/env python3
"""Ingest IPA FE past exams into Supabase quiz tables.

Usage:
  python scripts/ipa_ingest_quiz.py discover [--write]
  python scripts/ipa_ingest_quiz.py ingest --exam-id 2023r05 --kamoku A
  python scripts/ipa_ingest_quiz.py ingest --all [--force] [--skip-figures]
  python scripts/ipa_ingest_quiz.py verify --exam-id 2023r05 --kamoku B
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from urllib.request import urlretrieve

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from febot.config import Settings  # noqa: E402
from febot.ipa_extract import (  # noqa: E402
    build_default_tags,
    extract_pdf_text,
    extracted_to_qid,
    parse_ipa_kamoku_a,
    parse_ipa_kamoku_b,
)
from febot.ipa_figures import (  # noqa: E402
    assign_kamoku_a_visual_pages,
    assign_kamoku_b_question_pages,
    capture_pdf_pages,
)
from febot.llm_backend import get_openai_compat_backend  # noqa: E402
from febot.quiz_repair import extracted_to_repaired, repair_questions  # noqa: E402
from febot.supabase_quiz import (  # noqa: E402
    QuizAsset,
    QuizChoice,
    QuizExamRecord,
    QuizQuestionRecord,
    SupabaseQuizStore,
)

log = logging.getLogger(__name__)

MANIFEST_PATH = ROOT / "data" / "ipa_quiz_manifest.yaml"
CACHE_DIR = ROOT / "data" / ".ipa_cache"
IPA_INDEX_URL = "https://www.ipa.go.jp/shiken/mondai-kaiotu/sg_fe/koukai/index.html"


def _load_manifest() -> list[dict]:
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(f"Manifest not found: {MANIFEST_PATH}")
    data = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    return data.get("exams", [])


def _save_manifest(exams: list[dict]) -> None:
    MANIFEST_PATH.write_text(
        yaml.dump({"exams": exams}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _get_store() -> SupabaseQuizStore:
    load_dotenv(ROOT / ".env")
    url = os.environ.get("SUPABASE_URL", "").strip()
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

    if not url:
        raise RuntimeError("SUPABASE_URL is required")
    if not service_key:
        raise RuntimeError(
            "ingest には SUPABASE_SERVICE_KEY が必要です。\n"
            "anon キー（SUPABASE_KEY）では RLS により INSERT できません。\n"
            "Supabase Dashboard → Project Settings → API → service_role の secret を "
            ".env の SUPABASE_SERVICE_KEY に設定してください。"
        )
    return SupabaseQuizStore(url, service_key)


def _require_schema(store: SupabaseQuizStore) -> int:
    """Return 0 if quiz tables exist, else print hint and return 1."""
    status = store.check_schema()
    if status.get("ok"):
        return 0
    print("Supabase の quiz テーブルが見つかりません。")
    print(f"  接続先: {status.get('supabase_host', '?')}")
    for table, info in status.get("tables", {}).items():
        if not info.get("exists"):
            print(f"  - {table}: {info.get('code', '?')} {info.get('message', '')}")
    print()
    print("対処: Supabase Dashboard → SQL Editor で次を実行してください:")
    print(f"  {ROOT / 'supabase' / 'migrations' / '20260609_quiz_tables.sql'}")
    return 1


def _download_pdf(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1000:
        log.info("Using cached %s", dest)
        return dest
    log.info("Downloading %s", url)
    urlretrieve(url, dest)
    return dest


def _find_exam(manifest: list[dict], exam_id: str, kamoku: str) -> dict | None:
    for e in manifest:
        if e.get("exam_id") == exam_id and e.get("kamoku", "").upper() == kamoku.upper():
            return e
    return None


def cmd_discover(args: argparse.Namespace) -> int:
    import httpx

    manifest = _load_manifest()
    known = {(e["exam_id"], e["kamoku"].upper()) for e in manifest}

    resp = httpx.get(IPA_INDEX_URL, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    html = resp.text

    candidates: list[dict] = []
    for m in re.finditer(r'href="([^"]*koukai/(\d{4}r\d{2})\.html)"', html):
        page_path, exam_id = m.group(1), m.group(2)
        if not page_path.startswith("http"):
            page_path = f"https://www.ipa.go.jp/shiken/mondai-kaiotu/sg_fe/koukai/{exam_id}.html"
        for kamoku in ("A", "B"):
            key = (exam_id, kamoku)
            if key not in known:
                candidates.append(
                    {
                        "exam_id": exam_id,
                        "kamoku": kamoku,
                        "source_page_url": page_path,
                        "pdf_qs": f"(discover from {page_path})",
                        "pdf_ans": f"(discover from {page_path})",
                    }
                )

    if not candidates:
        print("No new exam candidates found.")
        return 0

    print(f"Found {len(candidates)} candidate(s):")
    for c in candidates:
        print(f"  - {c['exam_id']} 科目{c['kamoku']}")

    if args.write:
        manifest.extend(candidates)
        _save_manifest(manifest)
        print(f"Appended to {MANIFEST_PATH} (PDF URLs need manual update)")

    return 0


def _ingest_one(
    store: SupabaseQuizStore,
    entry: dict,
    *,
    force: bool = False,
    skip_figures: bool = False,
    skip_repair: bool = False,
) -> int:
    exam_id = entry["exam_id"]
    kamoku = entry["kamoku"].upper()
    pdf_qs_url = entry["pdf_qs"]
    pdf_ans_url = entry["pdf_ans"]

    if pdf_qs_url.startswith("(") or pdf_ans_url.startswith("("):
        log.error("PDF URLs not set for %s/%s — update manifest", exam_id, kamoku)
        return 1

    existing = store.get_exam(exam_id, kamoku)
    if existing and not force:
        log.info("Exam %s/%s already ingested (use --force to re-ingest)", exam_id, kamoku)
        return 0

    cache_key = f"{exam_id}-kamoku-{kamoku.lower()}"
    qs_path = _download_pdf(pdf_qs_url, CACHE_DIR / f"{cache_key}-qs.pdf")
    ans_path = _download_pdf(pdf_ans_url, CACHE_DIR / f"{cache_key}-ans.pdf")

    qs_text = extract_pdf_text(qs_path)
    ans_text = extract_pdf_text(ans_path)

    if kamoku == "A":
        extracted = parse_ipa_kamoku_a(qs_text, ans_text, exam_id)
        category = "科目A"
    else:
        extracted = parse_ipa_kamoku_b(qs_text, ans_text, exam_id)
        category = "科目B"

    if not extracted:
        log.error("No questions extracted for %s/%s", exam_id, kamoku)
        return 1

    log.info("Extracted %d questions for %s 科目%s", len(extracted), exam_id, kamoku)

    repaired = extracted_to_repaired(extracted, source_pdf_qs_url=pdf_qs_url)
    if not skip_repair:
        try:
            settings = Settings.load(require_slack=False)
            if settings.ai_api_key:
                llm = get_openai_compat_backend(settings)
                log.info(
                    "LLM repair via OpenAI-compatible API (model=%s)",
                    settings.ai_chat_model,
                )
                repaired = repair_questions(
                    llm,
                    extracted,
                    ans_text,
                    exam_id=exam_id,
                    kamoku=kamoku,
                    source_pdf_qs_url=pdf_qs_url,
                )
            else:
                log.warning("AI_API_KEY not set; using raw extraction with default explanations")
        except Exception as e:
            log.warning("LLM repair skipped: %s", e)

    figure_pages: dict[int, list[int]] = {}
    page_screenshots: dict[int, Path] = {}
    if not skip_figures:
        try:
            fig_dir = CACHE_DIR / cache_key / "figures"
            page_screenshots = capture_pdf_pages(qs_path, fig_dir)
            if kamoku == "B":
                figure_pages = assign_kamoku_b_question_pages(qs_path, extracted)
            else:
                figure_pages = assign_kamoku_a_visual_pages(qs_path, extracted)
        except Exception as e:
            log.warning("Figure capture skipped: %s", e)

    exam_uuid = store.upsert_exam(
        QuizExamRecord(
            exam_id=exam_id,
            kamoku=kamoku,
            exam_format=entry.get("exam_format", "cbt"),
            source_page_url=entry.get("source_page_url", ""),
            source_pdf_qs_url=pdf_qs_url,
            source_pdf_ans_url=pdf_ans_url,
            content_version=f"{exam_id}-{kamoku}-v1",
        )
    )

    ext_by_num = {q.question_number: q for q in extracted}
    records: list[QuizQuestionRecord] = []

    for rq in repaired:
        ext = ext_by_num.get(rq.question_number)
        has_figure = ext.has_figure_hint if ext else False
        tags = build_default_tags(exam_id, kamoku, has_figure)
        tags.append("source_ipa_official")

        assets: list[QuizAsset] = []
        page_nums = figure_pages.get(rq.question_number, [])
        for page_num in page_nums:
            local_path = page_screenshots.get(page_num)
            if not local_path or not local_path.is_file():
                continue
            storage_path = f"ipa/{exam_id}/kamoku-{kamoku.lower()}/q{rq.question_number:02d}/page-{page_num:02d}.png"
            caption = (
                f"問題文（ページ {page_num}）"
                if kamoku == "B"
                else f"問題・図表（ページ {page_num}）"
            )
            try:
                public_url = store.upload_asset(local_path, storage_path)
                assets.append(
                    QuizAsset(
                        type="image",
                        storage_path=storage_path,
                        public_url=public_url,
                        page=page_num,
                        caption=caption,
                    )
                )
            except Exception as e:
                log.warning(
                    "Failed to upload asset for q%d page %d: %s", rq.question_number, page_num, e
                )

        body = "" if kamoku == "B" and assets else rq.body
        records.append(
            QuizQuestionRecord(
                qid=extracted_to_qid(exam_id, kamoku, rq.question_number),
                question_number=rq.question_number,
                category=category,
                field="",
                body=body,
                choices=[QuizChoice(mark=m, text=t) for m, t in rq.choices],
                correct=rq.correct,
                explanation=rq.explanation,
                assets=assets,
                tags=tags,
                source_type="ipa_official",
            )
        )

    count = store.upsert_questions(exam_uuid, records)
    print(f"Ingested {count} questions for {exam_id} 科目{kamoku}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    store = _get_store()
    if _require_schema(store):
        return 1
    manifest = _load_manifest()

    if args.all:
        rc = 0
        for entry in manifest:
            if _ingest_one(
                store,
                entry,
                force=args.force,
                skip_figures=args.skip_figures,
                skip_repair=args.skip_repair,
            ):
                rc = 1
        return rc

    if not args.exam_id or not args.kamoku:
        print("Specify --exam-id and --kamoku, or use --all")
        return 1

    entry = _find_exam(manifest, args.exam_id, args.kamoku)
    if not entry:
        print(f"Exam {args.exam_id}/{args.kamoku} not in manifest")
        return 1

    return _ingest_one(
        store,
        entry,
        force=args.force,
        skip_figures=args.skip_figures,
        skip_repair=args.skip_repair,
    )


def cmd_check_schema(_args: argparse.Namespace) -> int:
    store = _get_store()
    return _require_schema(store)


def cmd_verify(args: argparse.Namespace) -> int:
    store = _get_store()
    if _require_schema(store):
        return 1
    if not args.exam_id or not args.kamoku:
        print("Specify --exam-id and --kamoku")
        return 1

    report = store.verify_exam(args.exam_id, args.kamoku.upper())
    if "error" in report:
        print(report["error"])
        return 1

    print(f"Exam: {report['exam_id']} 科目{report['kamoku']}")
    print(f"Questions: {report['question_count']}")
    print(f"With figures: {report['with_figures']}")
    for qid in report["qids"]:
        print(f"  - {qid}")
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="IPA quiz ingest to Supabase")
    sub = parser.add_subparsers(dest="command", required=True)

    p_discover = sub.add_parser("discover", help="Find new IPA exams")
    p_discover.add_argument("--write", action="store_true", help="Append to manifest")

    p_ingest = sub.add_parser("ingest", help="Ingest exam(s)")
    p_ingest.add_argument("--exam-id", help="Exam ID e.g. 2023r05")
    p_ingest.add_argument("--kamoku", help="A or B")
    p_ingest.add_argument("--all", action="store_true", help="Ingest all manifest entries")
    p_ingest.add_argument("--force", action="store_true", help="Re-ingest even if exists")
    p_ingest.add_argument("--skip-figures", action="store_true", help="Skip Playwright screenshots")
    p_ingest.add_argument("--skip-repair", action="store_true", help="Skip LLM repair")

    p_verify = sub.add_parser("verify", help="Verify ingested exam")
    p_verify.add_argument("--exam-id", required=True)
    p_verify.add_argument("--kamoku", required=True)

    sub.add_parser("check-schema", help="Verify quiz_exams/quiz_questions tables exist")

    args = parser.parse_args()
    if args.command == "discover":
        return cmd_discover(args)
    if args.command == "ingest":
        return cmd_ingest(args)
    if args.command == "verify":
        return cmd_verify(args)
    if args.command == "check-schema":
        return cmd_check_schema(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
