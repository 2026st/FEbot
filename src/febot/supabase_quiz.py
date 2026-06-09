"""Supabase storage for IPA quiz questions (separate from RAG corpus)."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from postgrest.exceptions import APIError

from febot.quiz import QuizItem, choices_to_markdown, format_qtype
from supabase import Client, create_client

log = logging.getLogger(__name__)

QUIZ_STORAGE_BUCKET = "quiz-assets"
MIGRATION_HINT = "supabase/migrations/20260609_quiz_tables.sql"


@dataclass(frozen=True)
class QuizAsset:
    type: str
    storage_path: str
    public_url: str
    page: int = 0
    caption: str = ""

    @staticmethod
    def from_dict(d: dict[str, Any]) -> QuizAsset:
        return QuizAsset(
            type=d.get("type", "image"),
            storage_path=d.get("storage_path", ""),
            public_url=d.get("public_url", ""),
            page=int(d.get("page", 0) or 0),
            caption=d.get("caption", "") or "",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "storage_path": self.storage_path,
            "public_url": self.public_url,
            "page": self.page,
            "caption": self.caption,
        }


@dataclass(frozen=True)
class QuizChoice:
    mark: str
    text: str

    @staticmethod
    def from_dict(d: dict[str, Any]) -> QuizChoice:
        return QuizChoice(mark=d["mark"], text=d.get("text", ""))

    def to_dict(self) -> dict[str, str]:
        return {"mark": self.mark, "text": self.text}


@dataclass
class QuizQuestionRecord:
    qid: str
    question_number: int
    category: str
    field: str
    body: str
    choices: list[QuizChoice]
    correct: str
    explanation: str
    assets: list[QuizAsset]
    tags: list[str]
    source_type: str = "ipa_official"
    content_hash: str = ""

    def compute_hash(self) -> str:
        payload = {
            "body": self.body,
            "choices": [c.to_dict() for c in self.choices],
            "correct": self.correct,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class QuizExamRecord:
    exam_id: str
    kamoku: str
    exam_format: str = "cbt"
    source_page_url: str = ""
    source_pdf_qs_url: str = ""
    source_pdf_ans_url: str = ""
    content_version: str = ""


def row_to_quiz_item(row: dict[str, Any], exam_meta: dict[str, Any] | None = None) -> QuizItem:
    """Convert a quiz_questions DB row to QuizItem."""
    choices_raw = row.get("choices") or []
    if isinstance(choices_raw, str):
        choices_raw = json.loads(choices_raw)
    choice_pairs = [(c["mark"], c.get("text", "")) for c in choices_raw]
    choices_md = choices_to_markdown(choice_pairs)

    assets_raw = row.get("assets") or []
    if isinstance(assets_raw, str):
        assets_raw = json.loads(assets_raw)
    image_urls = tuple(
        a.get("public_url", "")
        for a in assets_raw
        if a.get("type") == "image" and a.get("public_url")
    )

    tags_raw = row.get("tags") or []
    tags = tuple(tags_raw) if isinstance(tags_raw, list) else ()

    exam_id = (exam_meta or {}).get("exam_id", "")
    kamoku = (exam_meta or {}).get("kamoku", "")
    qtype = format_qtype(row.get("category", ""), exam_id, kamoku)

    source_url = (exam_meta or {}).get("source_pdf_qs_url", "") or row.get("source_url", "")

    return QuizItem(
        qid=row["qid"],
        qtype=qtype,
        body=row.get("body", ""),
        choices=choices_md,
        correct=row.get("correct", ""),
        explanation=row.get("explanation", ""),
        category=row.get("category", ""),
        field=row.get("field", "") or "",
        image_urls=image_urls,
        source_url=source_url,
        tags=tags,
    )


class SupabaseQuizStore:
    """CRUD for quiz_exams / quiz_questions and quiz-assets storage."""

    def __init__(self, url: str, key: str) -> None:
        self.client: Client = create_client(url, key)
        self.url = url.rstrip("/")

    def check_schema(self) -> dict[str, Any]:
        """Probe quiz tables; return status for preflight checks."""
        host = urlparse(self.url).netloc
        tables = ("quiz_exams", "quiz_questions")
        results: dict[str, Any] = {"supabase_host": host, "tables": {}}
        for table in tables:
            try:
                self.client.table(table).select("id").limit(1).execute()
                results["tables"][table] = {"exists": True}
            except APIError as e:
                err = e.args[0] if e.args else {}
                code = err.get("code", "") if isinstance(err, dict) else ""
                msg = err.get("message", str(e)) if isinstance(err, dict) else str(e)
                results["tables"][table] = {
                    "exists": False,
                    "code": code,
                    "message": msg,
                }
        results["ok"] = all(results["tables"].get(t, {}).get("exists") for t in tables)
        return results

    @staticmethod
    def _raise_rls_hint(exc: APIError, table: str, op: str) -> None:
        err = exc.args[0] if exc.args else {}
        code = err.get("code", "") if isinstance(err, dict) else ""
        if code in ("42501", "PGRST301"):
            raise RuntimeError(
                f"{table} への {op} が RLS で拒否されました（code={code}）。\n"
                "ingest には .env の SUPABASE_SERVICE_KEY（service_role secret）が必要です。\n"
                "SUPABASE_KEY（anon）では書き込めません。"
            ) from exc
        raise exc

    def load_all(self) -> list[QuizItem]:
        exams_result = self.client.table("quiz_exams").select("*").execute()
        exam_by_id = {e["id"]: e for e in (exams_result.data or [])}

        result = self.client.table("quiz_questions").select("*").execute()
        rows = result.data or []
        items: list[QuizItem] = []
        for row in rows:
            exam_meta = exam_by_id.get(row.get("exam_uuid"))
            items.append(row_to_quiz_item(row, exam_meta))
        log.info("Loaded %d quiz questions from Supabase", len(items))
        return items

    def count_by_category(self) -> dict[str, int]:
        items = self.load_all()
        counts: dict[str, int] = {}
        for it in items:
            cat = it.category or "unknown"
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def get_exam(self, exam_id: str, kamoku: str) -> dict[str, Any] | None:
        try:
            result = (
                self.client.table("quiz_exams")
                .select("*")
                .eq("exam_id", exam_id)
                .eq("kamoku", kamoku)
                .execute()
            )
            return result.data[0] if result.data else None
        except APIError as e:
            err = e.args[0] if e.args else {}
            code = err.get("code", "") if isinstance(err, dict) else ""
            if code == "PGRST205":
                raise RuntimeError(
                    f"テーブル quiz_exams が Supabase に存在しません（code={code}）。\n"
                    f"Supabase SQL Editor で {MIGRATION_HINT} を実行してください。"
                ) from e
            raise

    def upsert_exam(self, exam: QuizExamRecord) -> str:
        existing = self.get_exam(exam.exam_id, exam.kamoku)
        payload = {
            "exam_id": exam.exam_id,
            "kamoku": exam.kamoku,
            "exam_format": exam.exam_format,
            "source_page_url": exam.source_page_url,
            "source_pdf_qs_url": exam.source_pdf_qs_url,
            "source_pdf_ans_url": exam.source_pdf_ans_url,
            "content_version": exam.content_version,
            "ingested_at": "now()",
        }
        if existing:
            exam_uuid = existing["id"]
            try:
                self.client.table("quiz_exams").update(
                    {k: v for k, v in payload.items() if k != "ingested_at"}
                ).eq("id", exam_uuid).execute()
            except APIError as e:
                self._raise_rls_hint(e, "quiz_exams", "UPDATE")
            log.info("Updated quiz_exam %s/%s", exam.exam_id, exam.kamoku)
            return exam_uuid

        try:
            result = self.client.table("quiz_exams").insert(payload).execute()
        except APIError as e:
            self._raise_rls_hint(e, "quiz_exams", "INSERT")
        exam_uuid = result.data[0]["id"]
        log.info("Inserted quiz_exam %s/%s", exam.exam_id, exam.kamoku)
        return exam_uuid

    def upsert_questions(self, exam_uuid: str, questions: list[QuizQuestionRecord]) -> int:
        if not questions:
            return 0

        qids = [q.qid for q in questions]
        self.client.table("quiz_questions").delete().in_("qid", qids).execute()

        records = []
        for q in questions:
            content_hash = q.content_hash or q.compute_hash()
            records.append(
                {
                    "exam_uuid": exam_uuid,
                    "qid": q.qid,
                    "question_number": q.question_number,
                    "category": q.category,
                    "field": q.field,
                    "body": q.body,
                    "choices": [c.to_dict() for c in q.choices],
                    "correct": q.correct,
                    "explanation": q.explanation,
                    "assets": [a.to_dict() for a in q.assets],
                    "tags": q.tags,
                    "source_type": q.source_type,
                    "content_hash": content_hash,
                }
            )

        self.client.table("quiz_questions").insert(records).execute()
        log.info("Upserted %d quiz questions", len(records))
        return len(records)

    def upload_asset(self, local_path: Path, storage_path: str) -> str:
        """Upload image to quiz-assets bucket; return public URL."""
        content_type = "image/png"
        if local_path.suffix.lower() in (".jpg", ".jpeg"):
            content_type = "image/jpeg"

        with local_path.open("rb") as f:
            self.client.storage.from_(QUIZ_STORAGE_BUCKET).upload(
                storage_path,
                f.read(),
                {"content-type": content_type, "upsert": "true"},
            )

        public_url = f"{self.url}/storage/v1/object/public/{QUIZ_STORAGE_BUCKET}/{storage_path}"
        self._verify_public_asset(public_url, storage_path)
        log.info("Uploaded asset %s -> %s", storage_path, public_url)
        return public_url

    def _verify_public_asset(self, public_url: str, storage_path: str) -> None:
        import httpx

        resp = httpx.get(public_url, follow_redirects=True, timeout=30.0)
        content_type = resp.headers.get("content-type", "")
        if resp.status_code != 200 or not content_type.startswith("image/"):
            raise RuntimeError(
                f"Upload verification failed for {storage_path}: "
                f"status={resp.status_code} content-type={content_type!r}"
            )

    def verify_exam(self, exam_id: str, kamoku: str) -> dict[str, Any]:
        exam = self.get_exam(exam_id, kamoku)
        if not exam:
            return {"error": f"Exam {exam_id}/{kamoku} not found"}

        result = (
            self.client.table("quiz_questions")
            .select("qid,question_number,correct,assets,tags")
            .eq("exam_uuid", exam["id"])
            .execute()
        )
        rows = result.data or []
        with_figures = sum(1 for r in rows if "has_figure" in (r.get("tags") or []))
        return {
            "exam_id": exam_id,
            "kamoku": kamoku,
            "question_count": len(rows),
            "with_figures": with_figures,
            "qids": [r["qid"] for r in sorted(rows, key=lambda x: x["question_number"])],
        }
