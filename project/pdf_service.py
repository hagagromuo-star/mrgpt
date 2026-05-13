from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import fitz

from config import CACHE_DIR, DATA_DIR, MAX_EXTRACTED_LESSON_CHARS, MAX_TELEGRAM_MESSAGE, SUBJECTS


ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
PUNCTUATION = re.compile(r"[^\w\s\u0600-\u06FF]")


@dataclass(frozen=True)
class LessonMatch:
    page_index: int
    line_index: int
    score: float


async def extract_lesson_content(subject: str, lesson_name: str) -> str | None:
    return await asyncio.to_thread(_extract_lesson_content_sync, subject, lesson_name)


async def extract_subject_content(subject: str) -> str | None:
    return await asyncio.to_thread(_extract_subject_content_sync, subject)


def split_text(text: str, limit: int = MAX_TELEGRAM_MESSAGE) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut_at = remaining.rfind("\n", 0, limit)
        if cut_at < int(limit * 0.45):
            cut_at = remaining.rfind(" ", 0, limit)
        if cut_at < int(limit * 0.45):
            cut_at = limit
        chunks.append(remaining[:cut_at].strip())
        remaining = remaining[cut_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def normalize_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = ARABIC_DIACRITICS.sub("", text)
    text = text.replace("ـ", "")
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ؤ": "و",
        "ئ": "ي",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = PUNCTUATION.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_lesson_content_sync(subject: str, lesson_name: str) -> str | None:
    lesson_name = (lesson_name or "").strip()
    if not lesson_name:
        return None

    pdf_path = _get_pdf_path(subject)
    if not pdf_path or not pdf_path.exists():
        return None

    cache_file = _cache_path("lesson", subject, lesson_name, pdf_path)
    cached = _read_cache(cache_file)
    if cached:
        return cached

    pages = _read_pdf_pages(pdf_path)
    if not pages:
        return None

    match = _find_best_lesson_start(pages, lesson_name)
    if not match:
        return None

    query_norm = normalize_text(lesson_name)
    content = _collect_lesson_text(pages, match, query_norm)
    content = _clean_text(content)
    if len(normalize_text(content)) < 30:
        return None

    _write_cache(cache_file, content)
    return content


def _extract_subject_content_sync(subject: str) -> str | None:
    pdf_path = _get_pdf_path(subject)
    if not pdf_path or not pdf_path.exists():
        return None


    cache_file = _cache_path("full", subject, "full_pdf", pdf_path)
    cached = _read_cache(cache_file)
    if cached:
        return cached

    pages = _read_pdf_pages(pdf_path)
    content = _clean_text("\n\n".join(pages))
    if not content:
        return None
    _write_cache(cache_file, content)
    return content


def _get_pdf_path(subject: str) -> Path | None:
    subject_config = SUBJECTS.get(subject)
    if not subject_config:
        return None
    expected_path = DATA_DIR / subject_config["pdf"]
    if expected_path.exists():
        return expected_path

    expected_name = subject_config["pdf"].lower()
    try:
        for candidate in DATA_DIR.iterdir():
            if candidate.is_file() and candidate.name.lower() == expected_name:
                return candidate
    except OSError:
        return expected_path
    return expected_path


def _cache_path(kind: str, subject: str, name: str, pdf_path: Path) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    mtime = pdf_path.stat().st_mtime_ns if pdf_path.exists() else 0
    raw_key = f"{kind}:{subject}:{name}:{mtime}"
    key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:32]
    return CACHE_DIR / f"pdf_{kind}_{subject}_{key}.json"


def _read_cache(path: Path) -> str | None:
    try:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        text = str(payload.get("text") or "").strip()
        return text or None
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(path: Path, text: str) -> None:
    payload = {"text": text}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _read_pdf_pages(pdf_path: Path) -> list[str]:
    pages: list[str] = []
    try:
        with fitz.open(str(pdf_path)) as doc:
            for page in doc:
                pages.append(page.get_text("text") or "")
    except Exception:
        return []
    return pages


def _find_best_lesson_start(pages: list[str], lesson_name: str) -> LessonMatch | None:
    query = normalize_text(lesson_name)
    if not query:
        return None

    best_match: LessonMatch | None = None
    for page_index, page_text in enumerate(pages):
        for line_index, raw_line in enumerate(page_text.splitlines()):
            line = raw_line.strip()
            if not line:
                continue
            score = _match_score(query, normalize_text(line))
            if best_match is None or score > best_match.score:
                best_match = LessonMatch(page_index=page_index, line_index=line_index, score=score)

    if not best_match:
        return None

    threshold = 0.7 if len(query) <= 5 else 0.55
    return best_match if best_match.score >= threshold else None


def _match_score(query: str, candidate: str) -> float:
    if not query or not candidate:
        return 0.0
    if query == candidate:
        return 1.0
    if query in candidate or candidate in query:
        length_ratio = min(len(query), len(candidate)) / max(len(query), len(candidate))
        return max(0.82, length_ratio)

    query_tokens = set(query.split())
    candidate_tokens = set(candidate.split())
    overlap = 0.0
    if query_tokens:
        overlap = len(query_tokens & candidate_tokens) / len(query_tokens)

    similarity = SequenceMatcher(None, query, candidate).ratio()
    return max(similarity, overlap * 0.92)


def _collect_lesson_text(pages: list[str], match: LessonMatch, query_norm: str) -> str:
    collected: list[str] = []
    total_chars = 0

    for page_index in range(match.page_index, len(pages)):
        lines = pages[page_index].splitlines()
        start_line = match.line_index if page_index == match.page_index else 0

        for line_index in range(start_line, len(lines)):
            line = lines[line_index].strip()
            if not line:
                continue
            if total_chars > 1200 and _looks_like_new_lesson_heading(line, query_norm):
                return "\n".join(collected)

            collected.append(line)
            total_chars += len(line) + 1
            if total_chars >= MAX_EXTRACTED_LESSON_CHARS:
                return "\n".join(collected)

    return "\n".join(collected)


def _looks_like_new_lesson_heading(line: str, current_lesson_norm: str) -> bool:
    normalized = normalize_text(line)
    if not normalized or len(normalized) > 90:
        return False
    if current_lesson_norm and (current_lesson_norm in normalized or normalized in current_lesson_norm):
        return False

    heading_prefixes = (
        "الدرس",
        "درس",
        "الوحده",
        "الوحدة",
        "الفصل",
        "الموضوع",
        "unit",
        "lesson",
        "chapter",
    )
    return normalized.startswith(heading_prefixes)


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
