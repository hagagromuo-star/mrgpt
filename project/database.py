from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import aiosqlite

from config import CACHE_DIR, DATABASE_PATH, DATA_DIR, FREE_DAILY_LIMIT, SUBJECT_KEYS, VALID_PLANS


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _now_iso() -> str:
    return _now().isoformat()


def _today() -> str:
    return date.today().isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


async def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                created_at TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                plan TEXT,
                subject TEXT,
                expires_at TEXT,
                is_active INTEGER DEFAULT 1
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_limits (
                user_id INTEGER,
                date TEXT,
                count INTEGER,
                PRIMARY KEY(user_id, date)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                plan TEXT,
                status TEXT,
                created_at TEXT
            )
            """
        )
        await db.commit()


async def register_user(user_id: int, username: str | None, full_name: str | None) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username, full_name, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name
            """,
            (user_id, username or "", full_name or "", _now_iso()),
        )
        await db.commit()


async def consume_free_usage(user_id: int) -> bool:
    today = _today()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO usage_limits (user_id, date, count) VALUES (?, ?, 0)",
            (user_id, today),
        )
        cursor = await db.execute(
            "SELECT count FROM usage_limits WHERE user_id = ? AND date = ?",
            (user_id, today),
        )
        row = await cursor.fetchone()
        current_count = int(row[0]) if row else 0
        if current_count >= FREE_DAILY_LIMIT:
            return False
        await db.execute(
            "UPDATE usage_limits SET count = count + 1 WHERE user_id = ? AND date = ?",
            (user_id, today),
        )
        await db.commit()
        return True


async def get_usage_count(user_id: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT count FROM usage_limits WHERE user_id = ? AND date = ?",
            (user_id, _today()),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0


async def activate_subscription(user_id: int, plan: str, days: int) -> dict[str, Any]:
    plan = plan.strip().lower()
    if plan not in VALID_PLANS:
        raise ValueError("Invalid plan")
    if days <= 0:
        raise ValueError("Days must be positive")

    subject = plan if plan in SUBJECT_KEYS else None
    expires_at = (_now() + timedelta(days=days)).isoformat()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO subscriptions (user_id, plan, subject, expires_at, is_active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                plan = excluded.plan,
                subject = excluded.subject,
                expires_at = excluded.expires_at,
                is_active = 1
            """,
            (user_id, plan, subject, expires_at),
        )
        await db.execute(
            "INSERT INTO payments (user_id, plan, status, created_at) VALUES (?, ?, ?, ?)",
            (user_id, plan, "activated", _now_iso()),
        )
        await db.commit()

    return {"user_id": user_id, "plan": plan, "subject": subject, "expires_at": expires_at, "is_active": 1}


async def deactivate_subscription(user_id: int) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE subscriptions SET is_active = 0 WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_subscription_raw(user_id: int) -> dict[str, Any] | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM subscriptions WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_active_subscription(user_id: int) -> dict[str, Any] | None:
    subscription = await get_subscription_raw(user_id)
    if not subscription or int(subscription.get("is_active") or 0) != 1:
        return None

    expires_at = _parse_datetime(subscription.get("expires_at"))
    if not expires_at or expires_at < _now():
        await deactivate_subscription(user_id)
        return None
    return subscription


async def has_active_subscription(
    user_id: int,
    subject: str | None = None,
    vip_only: bool = False,
) -> bool:
    subscription = await get_active_subscription(user_id)
    if not subscription:
        return False

    plan = str(subscription.get("plan") or "").lower()
    subscribed_subject = str(subscription.get("subject") or "").lower()

    if vip_only:
        return plan == "vip"
    if subject is None:
        return True
    if plan in {"all", "vip"}:
        return True
    return plan == subject or subscribed_subject == subject


async def get_all_user_ids() -> list[int]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        rows = await cursor.fetchall()
        return [int(row[0]) for row in rows]


async def get_vip_user_ids() -> list[int]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT user_id FROM subscriptions
            WHERE plan = 'vip' AND is_active = 1 AND expires_at >= ?
            """,
            (_now_iso(),),
        )
        rows = await cursor.fetchall()
        return [int(row[0]) for row in rows]


async def get_user_status(user_id: int) -> dict[str, Any]:
    await get_active_subscription(user_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        user_cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user_row = await user_cursor.fetchone()

    subscription = await get_subscription_raw(user_id)
    usage_count = await get_usage_count(user_id)

    return {
        "user": dict(user_row) if user_row else None,
        "subscription": subscription,
        "usage_today": usage_count,
    }


async def get_stats() -> dict[str, int]:
    now = _now_iso()
    today = _today()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        total_users = await _fetch_count(db, "SELECT COUNT(*) FROM users")
        active_subscriptions = await _fetch_count(
            db,
            "SELECT COUNT(*) FROM subscriptions WHERE is_active = 1 AND expires_at >= ?",
            (now,),
        )
        active_vip = await _fetch_count(
            db,
            "SELECT COUNT(*) FROM subscriptions WHERE plan = 'vip' AND is_active = 1 AND expires_at >= ?",
            (now,),
        )
        total_payments = await _fetch_count(db, "SELECT COUNT(*) FROM payments")
        today_usage = await _fetch_count(
            db,
            "SELECT COALESCE(SUM(count), 0) FROM usage_limits WHERE date = ?",
            (today,),
        )

    return {
        "total_users": total_users,
        "active_subscriptions": active_subscriptions,
        "active_vip": active_vip,
        "total_payments": total_payments,
        "today_usage": today_usage,
    }


async def _fetch_count(
    db: aiosqlite.Connection,
    query: str,
    params: tuple[Any, ...] = (),
) -> int:
    cursor = await db.execute(query, params)
    row = await cursor.fetchone()
    return int(row[0]) if row else 0
