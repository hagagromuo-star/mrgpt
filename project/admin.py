from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from config import ADMIN_IDS, PLAN_LABELS, VALID_PLANS
from database import (
    activate_subscription,
    deactivate_subscription,
    get_all_user_ids,
    get_stats,
    get_user_status,
    get_vip_user_ids,
)
from keyboards import (
    BTN_ADMIN_ACTIVATE,
    BTN_ADMIN_BROADCAST,
    BTN_ADMIN_DEACTIVATE,
    BTN_ADMIN_SEND_VIP,
    BTN_ADMIN_STATS,
    BTN_ADMIN_STATUS,
    admin_panel_keyboard,
    main_keyboard,
)


router = Router()
logger = logging.getLogger(__name__)


class AdminPanelFlow(StatesGroup):
    activate_user_id = State()
    activate_plan = State()
    activate_days = State()
    deactivate_user_id = State()
    status_user_id = State()
    broadcast_message = State()
    vip_message = State()


@router.message(Command("admin"))
async def admin_help(message: Message) -> None:
    if not await _ensure_admin(message):
        return
    await message.answer(_admin_help_text(), reply_markup=admin_panel_keyboard())


@router.message(Command("admin_panel"))
async def admin_panel(message: Message) -> None:
    if not await _ensure_admin(message):
        return
    await message.answer("لوحة الأدمن جاهزة. اختار الأمر:", reply_markup=admin_panel_keyboard())


@router.message(Command("activate"))
async def activate_command(message: Message) -> None:
    if not await _ensure_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) != 4:
        await message.answer("الاستخدام: /activate user_id plan days")
        return
    try:
        user_id = int(parts[1])
        plan = parts[2].strip().lower()
        days = int(parts[3])
        await _activate_user(message, user_id, plan, days)
    except ValueError:
        await message.answer("اتأكد إن ID والأيام أرقام، والباقة صحيحة.")


@router.message(Command("deactivate"))
async def deactivate_command(message: Message) -> None:
    if not await _ensure_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("الاستخدام: /deactivate user_id")
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer("ID المستخدم لازم يكون رقم.")
        return
    await deactivate_subscription(user_id)
    await message.answer("تم إلغاء الاشتراك ✅")


@router.message(Command("status"))
async def status_command(message: Message) -> None:
    if not await _ensure_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("الاستخدام: /status user_id")
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer("ID المستخدم لازم يكون رقم.")
        return
    await _send_user_status(message, user_id)


@router.message(Command("broadcast"))
async def broadcast_command(message: Message, bot: Bot) -> None:
    if not await _ensure_admin(message):
        return
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.answer("الاستخدام: /broadcast الرسالة هنا")
        return
    await _broadcast_to_all(message, bot, text)


@router.message(Command("send_vip"))
async def send_vip_command(message: Message, bot: Bot) -> None:
    if not await _ensure_admin(message):
        return
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.answer("الاستخدام: /send_vip المحتوى هنا")
        return
    await _send_to_vip(message, bot, text)


@router.message(Command("stats"))
async def stats_command(message: Message) -> None:
    if not await _ensure_admin(message):
        return
    await _send_stats(message)


@router.message(F.text == BTN_ADMIN_ACTIVATE)
async def panel_activate(message: Message, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        return
    await state.clear()
    await state.set_state(AdminPanelFlow.activate_user_id)
    await message.answer("اكتب ID المستخدم اللي هتفعله:")


@router.message(F.text == BTN_ADMIN_DEACTIVATE)
async def panel_deactivate(message: Message, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        return
    await state.clear()
    await state.set_state(AdminPanelFlow.deactivate_user_id)
    await message.answer("اكتب ID المستخدم اللي هتلغي اشتراكه:")


@router.message(F.text == BTN_ADMIN_STATUS)
async def panel_status(message: Message, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        return
    await state.clear()
    await state.set_state(AdminPanelFlow.status_user_id)
    await message.answer("اكتب ID المستخدم اللي عايز تعرف حالته:")


@router.message(F.text == BTN_ADMIN_BROADCAST)
async def panel_broadcast(message: Message, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        return
    await state.clear()
    await state.set_state(AdminPanelFlow.broadcast_message)
    await message.answer("اكتب الرسالة الجماعية:")


@router.message(F.text == BTN_ADMIN_SEND_VIP)
async def panel_send_vip(message: Message, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        return
    await state.clear()
    await state.set_state(AdminPanelFlow.vip_message)
    await message.answer("اكتب رسالة VIP:")


@router.message(F.text == BTN_ADMIN_STATS)
async def panel_stats(message: Message) -> None:
    if not await _ensure_admin(message):
        return
    await _send_stats(message)


@router.message(AdminPanelFlow.activate_user_id)
async def panel_activate_user_id(message: Message, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        return
    try:
        user_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("اكتب ID صحيح بالأرقام.")
        return
    await state.update_data(user_id=user_id)
    await state.set_state(AdminPanelFlow.activate_plan)
    await message.answer(f"اكتب الباقة:\n{_plans_text()}")


@router.message(AdminPanelFlow.activate_plan)
async def panel_activate_plan(message: Message, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        return
    plan = (message.text or "").strip().lower()
    if plan not in VALID_PLANS:
        await message.answer(f"الباقة مش صحيحة. اختار واحدة من دول:\n{_plans_text()}")
        return
    await state.update_data(plan=plan)
    await state.set_state(AdminPanelFlow.activate_days)
    await message.answer("اكتب عدد أيام الاشتراك:")


@router.message(AdminPanelFlow.activate_days)
async def panel_activate_days(message: Message, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        return
    try:
        days = int((message.text or "").strip())
    except ValueError:
        await message.answer("عدد الأيام لازم يكون رقم.")
        return
    data = await state.get_data()
    await state.clear()
    await _activate_user(message, int(data["user_id"]), str(data["plan"]), days)


@router.message(AdminPanelFlow.deactivate_user_id)
async def panel_deactivate_user_id(message: Message, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        return
    try:
        user_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("اكتب ID صحيح بالأرقام.")
        return
    await state.clear()
    await deactivate_subscription(user_id)
    await message.answer("تم إلغاء الاشتراك ✅", reply_markup=admin_panel_keyboard())


@router.message(AdminPanelFlow.status_user_id)
async def panel_status_user_id(message: Message, state: FSMContext) -> None:
    if not await _ensure_admin(message):
        return
    try:
        user_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("اكتب ID صحيح بالأرقام.")
        return
    await state.clear()
    await _send_user_status(message, user_id)


@router.message(AdminPanelFlow.broadcast_message)
async def panel_broadcast_message(message: Message, state: FSMContext, bot: Bot) -> None:
    if not await _ensure_admin(message):
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("اكتب رسالة واضحة.")
        return
    await state.clear()
    await _broadcast_to_all(message, bot, text)


@router.message(AdminPanelFlow.vip_message)
async def panel_vip_message(message: Message, state: FSMContext, bot: Bot) -> None:
    if not await _ensure_admin(message):
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("اكتب رسالة واضحة.")
        return
    await state.clear()
    await _send_to_vip(message, bot, text)


async def _activate_user(message: Message, user_id: int, plan: str, days: int) -> None:
    try:
        subscription = await activate_subscription(user_id, plan, days)
    except ValueError:
        await message.answer(f"بيانات التفعيل مش صحيحة. الباقات المتاحة:\n{_plans_text()}")
        return
    await message.answer(
        "تم تفعيل الاشتراك ✅\n"
        f"ID: {subscription['user_id']}\n"
        f"الباقة: {PLAN_LABELS.get(subscription['plan'], subscription['plan'])}\n"
        f"ينتهي في: {subscription['expires_at']}",
        reply_markup=admin_panel_keyboard(),
    )


async def _send_user_status(message: Message, user_id: int) -> None:
    status = await get_user_status(user_id)
    user = status["user"] or {}
    subscription = status["subscription"] or {}
    plan = subscription.get("plan") or "لا يوجد"
    plan_label = PLAN_LABELS.get(str(plan), str(plan))
    active_text = "نشط" if int(subscription.get("is_active") or 0) == 1 else "غير نشط"
    await message.answer(
        "حالة المستخدم 🔍\n"
        f"ID: {user_id}\n"
        f"الاسم: {user.get('full_name') or 'مش مسجل'}\n"
        f"اليوزر: @{user.get('username') or 'بدون'}\n"
        f"الباقة: {plan_label}\n"
        f"الحالة: {active_text}\n"
        f"ينتهي في: {subscription.get('expires_at') or 'لا يوجد'}\n"
        f"استخدامات النهارده: {status['usage_today']}",
        reply_markup=admin_panel_keyboard(),
    )


async def _send_stats(message: Message) -> None:
    stats = await get_stats()
    await message.answer(
        "الإحصائيات 📊\n"
        f"عدد المستخدمين: {stats['total_users']}\n"
        f"الاشتراكات النشطة: {stats['active_subscriptions']}\n"
        f"VIP نشط: {stats['active_vip']}\n"
        f"عمليات التفعيل: {stats['total_payments']}\n"
        f"استخدامات النهارده: {stats['today_usage']}",
        reply_markup=admin_panel_keyboard(),
    )


async def _broadcast_to_all(message: Message, bot: Bot, text: str) -> None:
    user_ids = await get_all_user_ids()
    sent, failed = await _send_bulk(bot, user_ids, text)
    await message.answer(f"تم إرسال الرسالة ✅\nوصلت: {sent}\nفشل: {failed}", reply_markup=admin_panel_keyboard())


async def _send_to_vip(message: Message, bot: Bot, text: str) -> None:
    user_ids = await get_vip_user_ids()
    sent, failed = await _send_bulk(bot, user_ids, text)
    await message.answer(f"تم إرسال VIP ✅\nوصلت: {sent}\nفشل: {failed}", reply_markup=admin_panel_keyboard())


async def _send_bulk(bot: Bot, user_ids: list[int], text: str) -> tuple[int, int]:
    sent = 0
    failed = 0
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text)
            sent += 1
        except Exception:
            failed += 1
            logger.exception("Failed to send bulk message to %s", user_id)
        await asyncio.sleep(0.04)
    return sent, failed


async def _ensure_admin(message: Message) -> bool:
    if message.from_user and message.from_user.id in ADMIN_IDS:
        return True
    await message.answer("الأمر ده للأدمن بس.", reply_markup=main_keyboard())
    return False


def _admin_help_text() -> str:
    return """أوامر الأدمن:

/activate user_id plan days
/deactivate user_id
/status user_id
/broadcast الرسالة هنا
/send_vip المحتوى هنا
/stats
/admin_panel

الباقات:
arabic, english, math, science, studies, all, vip"""


def _plans_text() -> str:
    return "\n".join(f"{key}: {label}" for key, label in PLAN_LABELS.items())
