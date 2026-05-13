from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from config import (
    CACHE_DIR,
    MAX_FULL_EXAM_INPUT_CHARS,
    MAX_LESSON_INPUT_CHARS,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
)


_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client


async def generate_lesson_explanation(lesson_content: str) -> str:
    lesson_content = _trim_text(lesson_content, MAX_LESSON_INPUT_CHARS)
    prompt = f"""
أنت مدرس شاطر للصف الثالث الإعدادي المصري.
هذا نص الدرس من الكتاب:

{lesson_content}

اشرحه للطالب باللهجة المصرية بطريقة سهلة جدًا.

رتب الرد:
1. فكرة الدرس
2. شرح مبسط
3. أمثلة
4. أهم الملاحظات
5. أخطاء شائعة
6. أسئلة تدريبية
""".strip()
    return await _chat(prompt, cache_prefix="lesson_explanation", max_tokens=2200)


async def generate_lesson_summary(lesson_content: str) -> str:
    lesson_content = _trim_text(lesson_content, MAX_LESSON_INPUT_CHARS)
    prompt = f"""
لخص هذا الدرس لطلاب الصف الثالث الإعدادي المصري.

الدرس:
{lesson_content}

المطلوب:
- ملخص سريع
- أهم النقاط
- القوانين
- التعريفات
- مراجعة 5 دقائق
- أسئلة متوقعة
""".strip()
    return await _chat(prompt, cache_prefix="lesson_summary", max_tokens=1800)


async def generate_lesson_quiz(lesson_content: str, difficulty: str) -> list[dict[str, Any]]:
    lesson_content = _trim_text(lesson_content, MAX_LESSON_INPUT_CHARS)
    prompt = f"""
أنت واضع امتحانات محترف للصف الثالث الإعدادي المصري.

هذا محتوى الدرس:
{lesson_content}

أنشئ 10 أسئلة اختيار من متعدد.

الصعوبة:
{difficulty}

أعد الرد بصيغة JSON فقط:

[
  {{
    "question": "...",
    "choices": ["نص الاختيار الأول", "نص الاختيار الثاني", "نص الاختيار الثالث", "نص الاختيار الرابع"],
    "correct_index": 0,
    "explanation": "..."
  }}
]
""".strip()
    raw = await _chat(prompt, cache_prefix="lesson_quiz", max_tokens=3800)
    return _parse_questions(raw, expected_count=10)


async def generate_full_exam(subject_content: str, difficulty: str) -> list[dict[str, Any]]:
    subject_content = _trim_text(subject_content, MAX_FULL_EXAM_INPUT_CHARS)
    prompt = f"""
أنت واضع امتحانات محترف للصف الثالث الإعدادي المصري.

هذا محتوى المنهج:
{subject_content}

أنشئ امتحان شامل من 20 سؤال اختيار من متعدد.

الصعوبة:
{difficulty}

أعد الرد بصيغة JSON فقط:

[
  {{
    "question": "...",
    "choices": ["نص الاختيار الأول", "نص الاختيار الثاني", "نص الاختيار الثالث", "نص الاختيار الرابع"],
    "correct_index": 0,
    "explanation": "..."
  }}
]
""".strip()
    raw = await _chat(prompt, cache_prefix="full_exam", max_tokens=6200)
    return _parse_questions(raw, expected_count=20)


async def generate_study_plan(first_exam_date: str, study_hours: str, weak_subjects: str) -> str:
    prompt = f"""
أنشئ خطة مذاكرة يومية لطالب صف ثالث إعدادي في مصر.

المعطيات:
- تاريخ أول امتحان: {first_exam_date}
- ساعات المذاكرة: {study_hours}
- المواد الضعيفة: {weak_subjects}

المطلوب:
- جدول يومي
- مراجعات
- امتحانات
- نصائح
""".strip()
    return await _chat(prompt, cache_prefix="study_plan", max_tokens=2200)


async def generate_vip_content() -> str:
    prompt = """
أنت مدرس شاطر للصف الثالث الإعدادي المصري.

اعمل محتوى VIP يومي باللهجة المصرية للطلاب، ويكون منظم كده:
- ملخص يومي سريع
- كويز قصير من 5 أسئلة
- واجب بسيط
- نصائح مذاكرة عملية

خلي الكلام واضح ومش طويل زيادة.
""".strip()
    return await _chat(prompt, cache_prefix="vip_daily", max_tokens=1800)


async def _chat(prompt: str, cache_prefix: str, max_tokens: int) -> str:
    cache_file = _cache_file(cache_prefix, prompt)
    cached = _read_cached_text(cache_file)
    if cached:
        return cached

    response = await _get_client().chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=OPENAI_TEMPERATURE,
        max_tokens=max_tokens,
    )
    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("OpenAI returned an empty response")
    _write_cached_text(cache_file, text)
    return text


def _trim_text(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\n[تم اختصار جزء من النص لتقليل تكلفة المعالجة.]"


def _cache_file(prefix: str, prompt: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    raw_key = f"{OPENAI_MODEL}:{OPENAI_TEMPERATURE}:{prompt}"
    key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:40]
    return CACHE_DIR / f"ai_{prefix}_{key}.json"


def _read_cached_text(path: Path) -> str | None:
    try:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        text = str(payload.get("text") or "").strip()
        return text or None
    except (OSError, json.JSONDecodeError):
        return None


def _write_cached_text(path: Path, text: str) -> None:
    path.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")


def _parse_questions(raw_text: str, expected_count: int) -> list[dict[str, Any]]:
    json_text = _extract_json_array(raw_text)
    data = json.loads(json_text)
    if isinstance(data, dict) and "questions" in data:
        data = data["questions"]
    if not isinstance(data, list):
        raise ValueError("Quiz response is not a JSON list")

    questions: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        choices = item.get("choices") or []
        if not isinstance(choices, list):
            continue
        normalized_choices = [str(choice).strip() for choice in choices[:4]]
        try:
            correct_index = int(item.get("correct_index"))
        except (TypeError, ValueError):
            continue
        explanation = str(item.get("explanation") or "").strip()

        if not question or len(normalized_choices) != 4 or not 0 <= correct_index <= 3:
            continue

        questions.append(
            {
                "question": question,
                "choices": normalized_choices,
                "correct_index": correct_index,
                "explanation": explanation,
            }
        )
        if len(questions) == expected_count:
            break

    if not questions:
        raise ValueError("No valid questions returned")
    return questions


def _extract_json_array(text: str) -> str:
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON array was not found")
    return text[start : end + 1]
