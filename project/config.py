from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@YourUsername").strip() or "@YourUsername"

DATABASE_PATH = BASE_DIR / "bot.db"
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = BASE_DIR / "cache"

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
OPENAI_TEMPERATURE = 0.7

FREE_DAILY_LIMIT = 3
MAX_TELEGRAM_MESSAGE = 3900
MAX_LESSON_INPUT_CHARS = int(os.getenv("MAX_LESSON_INPUT_CHARS", "12000"))
MAX_FULL_EXAM_INPUT_CHARS = int(os.getenv("MAX_FULL_EXAM_INPUT_CHARS", "22000"))
MAX_EXTRACTED_LESSON_CHARS = int(os.getenv("MAX_EXTRACTED_LESSON_CHARS", "18000"))


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            ids.add(int(item))
        except ValueError:
            continue
    return ids


ADMIN_IDS = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))

SUBJECTS = {
    "arabic": {"label": "عربي", "pdf": "arabic.pdf"},
    "english": {"label": "إنجليزي", "pdf": "english.pdf"},
    "math": {"label": "رياضيات", "pdf": "math.pdf"},
    "science": {"label": "علوم", "pdf": "science.pdf"},
    "studies": {"label": "دراسات", "pdf": "studies.pdf"},
}

SUBJECT_LABELS = {value["label"]: key for key, value in SUBJECTS.items()}
SUBJECT_KEYS = set(SUBJECTS.keys())

VALID_PLANS = SUBJECT_KEYS | {"all", "vip"}
PLAN_LABELS = {
    "arabic": "عربي",
    "english": "إنجليزي",
    "math": "رياضيات",
    "science": "علوم",
    "studies": "دراسات",
    "all": "كل المواد",
    "vip": "VIP كامل",
}
