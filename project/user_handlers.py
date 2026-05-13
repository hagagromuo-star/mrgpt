from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ai_service import (
    generate_full_exam,
    generate_lesson_explanation,
    generate_lesson_quiz,
    generate_lesson_summary,
    generate_study_plan,
    generate_vip_content,
)
from config import ADMIN_USERNAME, PLAN_LABELS, SUBJECT_LABELS, SUBJECTS
from database import consume_free_usage, has_active_subscription, register_user
from keyboards import (
    ANSWER_LABELS,
    BTN_ACCOUNT_ID,
    BTN_CONTACT_ADMIN,
    BTN_DAILY_VIP,
    BTN_EXPLAIN,
    BTN_FULL_EXAM,
    BTN_LESSON_QUIZ,
    BTN_STUDY_PLAN,
    BTN_SUBSCRIBE,
    BTN_SUMMARY,
    DIFFICULTIES,
    answer_keyboard,
    difficulty_keyboard,
    main_keyboard,
    subjects_keyboard,
)
from pdf_service import extract_lesson_content, extract_subject_content, split_text


router = Router()
logger = logging.getLogger(__name__)

FREE_LIMIT_MESSAGE = """لقد استخدمت الحد المجاني اليومي 🔒

للاستمرار:
اشترك من زر 💳 الاشتراك"""

PROBLEM_MESSAGE = """حصلت مشكلة بسيطة 😅
جرّب تاني بعد دقيقة."""

LESSON_NOT_FOUND_MESSAGE = "مش لاقي الدرس ده حاليًا 😅"

user_sessions: dict[int, dict[str, Any]] = {}


class LessonFlow(StatesGroup):
    choosing_subject = State()
    waiting_lesson = State()
    choosing_difficulty = State()


class FullExamFlow(StatesGroup):
    choosing_subject = State()
    choosing_difficulty = State()


class StudyPlanFlow(StatesGroup):
    waiting_date = State()
    waiting_hours = State()
    waiting_weak_subjects = State()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _register_message_user(message)
    await message.answer(
        "أهلا بيك في مستر المراجعة 👋\nاختار اللي محتاجه من القائمة، وأنا هساعدك خطوة بخطوة.",
        reply_markup=main_keyboard(),
    )


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("تمام، رجعناك للقائمة الرئيسية.", reply_markup=main_keyboard())


@router.message(F.text.in_({BTN_EXPLAIN, BTN_SUMMARY, BTN_LESSON_QUIZ}))
async def start_lesson_flow(message: Message, state: FSMContext) -> None:
    await _register_message_user(message)
    action_by_button = {
        BTN_EXPLAIN: "explain",
        BTN_SUMMARY: "summary",
        BTN_LESSON_QUIZ: "lesson_quiz",
    }
    await state.clear()
    await state.update_data(action=action_by_button[message.text or ""])
    await state.set_state(LessonFlow.choosing_subject)
    await message.answer("اختار المادة الأول:", reply_markup=subjects_keyboard())


@router.message(F.text == BTN_FULL_EXAM)
async def start_full_exam_flow(message: Message, state: FSMContext) -> None:
    await _register_message_user(message)
    await state.clear()
    await state.set_state(FullExamFlow.choosing_subject)
    await message.answer("اختار المادة اللي عايز امتحان شامل عليها:", reply_markup=subjects_keyboard())


@router.message(F.text == BTN_STUDY_PLAN)
async def start_study_plan(message: Message, state: FSMContext) -> None:
    await _register_message_user(message)
    await state.clear()
    await state.set_state(StudyPlanFlow.waiting_date)
    await message.answer("اكتب تاريخ أول امتحان عندك. مثال: 2026-05-25", reply_markup=main_keyboard())


@router.message(F.text == BTN_DAILY_VIP)
async def daily_vip(message: Message) -> None:
    await _register_message_user(message)
    if not message.from_user:
        return
    try:
        if not await has_active_subscription(message.from_user.id, vip_only=True):
            await message.answer(_subscription_message(), reply_markup=main_keyboard())
            return

        await message.answer("ثواني أجهزلك محتوى VIP بتاع النهارده...")
        content = await generate_vip_content()
        await _send_long_message(message, content, with_main_keyboard=True)
    except Exception:
        logger.exception("Failed to generate VIP content")
        await message.answer(PROBLEM_MESSAGE, reply_markup=main_keyboard())


@router.message(F.text == BTN_SUBSCRIBE)
async def subscription_info(message: Message) -> None:
    await _register_message_user(message)
    await message.answer(_subscription_message(), reply_markup=main_keyboard())


@router.message(F.text == BTN_ACCOUNT_ID)
async def account_id(message: Message) -> None:
    await _register_message_user(message)
    if not message.from_user:
        return
    await message.answer(
        f"""رقم حسابك هو:

{message.from_user.id}

ابعت الرقم ده مع سكرين التحويل للأدمن.""",
        reply_markup=main_keyboard(),
    )


@router.message(F.text == BTN_CONTACT_ADMIN)
async def contact_admin(message: Message) -> None:
    await _register_message_user(message)
    await message.answer(f"للتواصل:\n{ADMIN_USERNAME}", reply_markup=main_keyboard())


@router.message(LessonFlow.choosing_subject)
async def choose_lesson_subject(message: Message, state: FSMContext) -> None:
    subject = _subject_from_label(message.text)
    if not subject:
        await message.answer("اختار مادة من الأزرار يا بطل.", reply_markup=subjects_keyboard())
        return

    await state.update_data(subject=subject)
    await state.set_state(LessonFlow.waiting_lesson)
    await message.answer("اكتب اسم الدرس زي ما تعرفه، حتى لو مش مطابق 100%.", reply_markup=main_keyboard())


@router.message(LessonFlow.waiting_lesson)
async def receive_lesson_name(message: Message, state: FSMContext) -> None:
    lesson_name = (message.text or "").strip()
    if not lesson_name:
        await message.answer("اكتب اسم الدرس عشان أقدر أدور عليه.")
        return

    data = await state.get_data()
    action = data.get("action")
    subject = data.get("subject")
    if not subject or not action:
        await state.clear()
        await message.answer("ابدأ من القائمة الرئيسية تاني.", reply_markup=main_keyboard())
        return

    if action == "lesson_quiz":
        await state.update_data(lesson_name=lesson_name)
        await state.set_state(LessonFlow.choosing_difficulty)
        await message.answer("اختار مستوى الصعوبة:", reply_markup=difficulty_keyboard())
        return

    await _process_lesson_text_action(message, state, subject, lesson_name, action)


@router.message(LessonFlow.choosing_difficulty)
async def choose_lesson_quiz_difficulty(message: Message, state: FSMContext, bot: Bot) -> None:
    difficulty = (message.text or "").strip()
    if difficulty not in DIFFICULTIES:
        await message.answer("اختار الصعوبة من الأزرار: سهل، متوسط، صعب.", reply_markup=difficulty_keyboard())
        return

    data = await state.get_data()
    subject = data.get("subject")
    lesson_name = data.get("lesson_name")
    if not subject or not lesson_name:
        await state.clear()
        await message.answer("ابدأ من القائمة الرئيسية تاني.", reply_markup=main_keyboard())
        return

    await _process_lesson_quiz(message, state, bot, subject, lesson_name, difficulty)


@router.message(FullExamFlow.choosing_subject)
async def choose_full_exam_subject(message: Message, state: FSMContext) -> None:
    subject = _subject_from_label(message.text)
    if not subject:
        await message.answer("اختار مادة من الأزرار يا بطل.", reply_markup=subjects_keyboard())
        return

    await state.update_data(subject=subject)
    await state.set_state(FullExamFlow.choosing_difficulty)
    await message.answer("اختار مستوى صعوبة الامتحان:", reply_markup=difficulty_keyboard())


@router.message(FullExamFlow.choosing_difficulty)
async def choose_full_exam_difficulty(message: Message, state: FSMContext, bot: Bot) -> None:
    difficulty = (message.text or "").strip()
    if difficulty not in DIFFICULTIES:
        await message.answer("اختار الصعوبة من الأزرار: سهل، متوسط، صعب.", reply_markup=difficulty_keyboard())
        return

    data = await state.get_data()
    subject = data.get("subject")
    if not subject:
        await state.clear()
        await message.answer("ابدأ من القائمة الرئيسية تاني.", reply_markup=main_keyboard())
        return

    try:
        await message.answer("تمام، بقرأ ملف المادة وبجهز الامتحان...")
        subject_content = await extract_subject_content(subject)
        if not subject_content:
            await state.clear()
            await message.answer("مش قادر أقرأ ملف المادة دي حاليًا 😅", reply_markup=main_keyboard())
            return
        if not await _ensure_feature_access(message, subject=subject):
            await state.clear()
            return

        questions = await generate_full_exam(subject_content, difficulty)
        await state.clear()
        await _start_quiz(
            message,
            bot,
            questions,
            title=f"امتحان شامل - {SUBJECTS[subject]['label']} - {difficulty}",
        )
    except Exception:
        logger.exception("Failed to build full exam")
        await state.clear()
        await message.answer(PROBLEM_MESSAGE, reply_markup=main_keyboard())


@router.message(StudyPlanFlow.waiting_date)
async def study_plan_date(message: Message, state: FSMContext) -> None:
    first_exam_date = (message.text or "").strip()
    if not first_exam_date:
        await message.answer("اكتب تاريخ أول امتحان عندك.")
        return
    await state.update_data(first_exam_date=first_exam_date)
    await state.set_state(StudyPlanFlow.waiting_hours)
    await message.answer("هتذاكر كام ساعة في اليوم؟")


@router.message(StudyPlanFlow.waiting_hours)
async def study_plan_hours(message: Message, state: FSMContext) -> None:
    study_hours = (message.text or "").strip()
    if not study_hours:
        await message.answer("اكتب عدد ساعات المذاكرة في اليوم.")
        return
    await state.update_data(study_hours=study_hours)
    await state.set_state(StudyPlanFlow.waiting_weak_subjects)
    await message.answer("اكتب المواد الضعيفة عندك. مثال: رياضيات وعلوم")


@router.message(StudyPlanFlow.waiting_weak_subjects)
async def study_plan_subjects(message: Message, state: FSMContext) -> None:
    weak_subjects = (message.text or "").strip()
    if not weak_subjects:
        await message.answer("اكتب المواد اللي محتاج تقويها.")
        return

    data = await state.get_data()
    try:
        if not await _ensure_feature_access(message):
            await state.clear()
            return
        await message.answer("تمام، بجهزلك خطة مذاكرة مناسبة...")
        plan = await generate_study_plan(
            first_exam_date=str(data.get("first_exam_date") or ""),
            study_hours=str(data.get("study_hours") or ""),
            weak_subjects=weak_subjects,
        )
        await state.clear()
        await _send_long_message(message, plan, with_main_keyboard=True)
    except Exception:
        logger.exception("Failed to generate study plan")
        await state.clear()
        await message.answer(PROBLEM_MESSAGE, reply_markup=main_keyboard())


@router.callback_query(F.data.startswith("answer:"))
async def handle_quiz_answer(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("إجابة مش واضحة.", show_alert=True)
        return

    try:
        question_index = int(parts[1])
        answer_index = int(parts[2])
    except ValueError:
        await callback.answer("إجابة مش واضحة.", show_alert=True)
        return

    session = user_sessions.get(callback.from_user.id)
    if not session:
        await callback.answer("مفيش امتحان شغال دلوقتي.", show_alert=True)
        await callback.message.answer("ابدأ امتحان جديد من القائمة.", reply_markup=main_keyboard())
        return

    current_index = int(session.get("current", 0))
    if question_index != current_index:
        await callback.answer("السؤال ده اتجاوب خلاص.")
        return

    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    questions = session["questions"]
    current_question = questions[current_index]
    session["answers"].append(answer_index)
    session["current"] = current_index + 1

    correct_index = int(current_question["correct_index"])
    if answer_index == correct_index:
        await callback.message.answer("إجابة صح ✅")
    else:
        await callback.message.answer(f"مش صح. الإجابة الصح: {ANSWER_LABELS[correct_index]} ✅")

    await _send_current_question(bot, callback.message.chat.id, callback.from_user.id)


@router.message()
async def fallback(message: Message) -> None:
    await _register_message_user(message)
    await message.answer("اختار من الأزرار اللي تحت عشان أساعدك أسرع.", reply_markup=main_keyboard())


async def _process_lesson_text_action(
    message: Message,
    state: FSMContext,
    subject: str,
    lesson_name: str,
    action: str,
) -> None:
    try:
        await message.answer("تمام، بدور على الدرس في ملف المادة...")
        lesson_content = await extract_lesson_content(subject, lesson_name)
        if not lesson_content:
            await state.clear()
            await message.answer(LESSON_NOT_FOUND_MESSAGE, reply_markup=main_keyboard())
            return
        if not await _ensure_feature_access(message, subject=subject):
            await state.clear()
            return

        if action == "explain":
            await message.answer("لقيت الدرس. ثواني وأشرحهولك بطريقة سهلة...")
            result = await generate_lesson_explanation(lesson_content)
        else:
            await message.answer("لقيت الدرس. ثواني وألخصهولك...")
            result = await generate_lesson_summary(lesson_content)

        await state.clear()
        await _send_long_message(message, result, with_main_keyboard=True)
    except Exception:
        logger.exception("Failed to process lesson text action")
        await state.clear()
        await message.answer(PROBLEM_MESSAGE, reply_markup=main_keyboard())


async def _process_lesson_quiz(
    message: Message,
    state: FSMContext,
    bot: Bot,
    subject: str,
    lesson_name: str,
    difficulty: str,
) -> None:
    try:
        await message.answer("تمام، بدور على الدرس وبجهز الأسئلة...")
        lesson_content = await extract_lesson_content(subject, lesson_name)
        if not lesson_content:
            await state.clear()
            await message.answer(LESSON_NOT_FOUND_MESSAGE, reply_markup=main_keyboard())
            return
        if not await _ensure_feature_access(message, subject=subject):
            await state.clear()
            return

        questions = await generate_lesson_quiz(lesson_content, difficulty)
        await state.clear()
        await _start_quiz(
            message,
            bot,
            questions,
            title=f"امتحان درس: {lesson_name} - {difficulty}",
        )
    except Exception:
        logger.exception("Failed to process lesson quiz")
        await state.clear()
        await message.answer(PROBLEM_MESSAGE, reply_markup=main_keyboard())


async def _start_quiz(message: Message, bot: Bot, questions: list[dict[str, Any]], title: str) -> None:
    if not message.from_user:
        return
    if not questions:
        await message.answer(PROBLEM_MESSAGE, reply_markup=main_keyboard())
        return

    user_sessions[message.from_user.id] = {
        "title": title,
        "questions": questions,
        "answers": [],
        "current": 0,
    }
    await message.answer(f"{title}\nالامتحان جاهز. جاوب سؤال سؤال 👇")
    await _send_current_question(bot, message.chat.id, message.from_user.id)


async def _send_current_question(bot: Bot, chat_id: int, user_id: int) -> None:
    session = user_sessions.get(user_id)
    if not session:
        return

    questions = session["questions"]
    current = int(session.get("current", 0))
    if current >= len(questions):
        await _finish_quiz(bot, chat_id, user_id)
        return

    question = questions[current]
    await bot.send_message(
        chat_id,
        _format_question(question, current + 1, len(questions)),
        reply_markup=answer_keyboard(current),
    )


async def _finish_quiz(bot: Bot, chat_id: int, user_id: int) -> None:
    session = user_sessions.pop(user_id, None)
    if not session:
        return

    questions = session["questions"]
    answers = session["answers"]
    score = sum(
        1 for question, answer in zip(questions, answers) if int(question["correct_index"]) == int(answer)
    )
    total = len(questions)

    lines = [
        "الامتحان خلص 🎉",
        f"درجتك: {score} من {total}",
        "",
        "التصحيح:",
    ]

    wrong_count = 0
    for index, (question, answer) in enumerate(zip(questions, answers), start=1):
        correct_index = int(question["correct_index"])
        if int(answer) == correct_index:
            continue
        wrong_count += 1
        choices = question["choices"]
        chosen = choices[answer] if 0 <= int(answer) < len(choices) else "إجابة غير واضحة"
        correct = choices[correct_index]
        explanation = question.get("explanation") or "راجع النقطة دي من الدرس."
        lines.extend(
            [
                f"س{index}: {question['question']}",
                f"إجابتك: {chosen}",
                f"الصح: {correct}",
                f"الشرح: {explanation}",
                "",
            ]
        )

    if wrong_count == 0:
        lines.append("ممتاز جدًا، كل إجاباتك صح ✅")

    chunks = split_text("\n".join(lines))
    for index, chunk in enumerate(chunks):
        await bot.send_message(
            chat_id,
            chunk,
            reply_markup=main_keyboard() if index == len(chunks) - 1 else None,
        )


def _format_question(question: dict[str, Any], index: int, total: int) -> str:
    choices = question["choices"]
    lines = [f"سؤال {index} من {total}", "", str(question["question"]), ""]
    for choice_index, choice_text in enumerate(choices[:4]):
        lines.append(f"{ANSWER_LABELS[choice_index]}) {choice_text}")
    return "\n".join(lines)


async def _ensure_feature_access(message: Message, subject: str | None = None) -> bool:
    if not message.from_user:
        return False

    user_id = message.from_user.id
    if await has_active_subscription(user_id, subject=subject):
        return True
    if await consume_free_usage(user_id):
        return True

    await message.answer(FREE_LIMIT_MESSAGE, reply_markup=main_keyboard())
    return False


async def _send_long_message(message: Message, text: str, with_main_keyboard: bool = False) -> None:
    chunks = split_text(text)
    if not chunks:
        await message.answer(PROBLEM_MESSAGE, reply_markup=main_keyboard() if with_main_keyboard else None)
        return
    for index, chunk in enumerate(chunks):
        await message.answer(
            chunk,
            reply_markup=main_keyboard() if with_main_keyboard and index == len(chunks) - 1 else None,
        )


async def _register_message_user(message: Message) -> None:
    if not message.from_user:
        return
    await register_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )


def _subject_from_label(text: str | None) -> str | None:
    return SUBJECT_LABELS.get((text or "").strip())


def _subscription_message() -> str:
    return """الباقات المتاحة 💳

- مادة واحدة: 69 جنيه
- كل المواد 192 جنيه
- VIP كامل: 242 جنيه

طريقة الاشتراك:
1. حوّل على فودافون كاش:
01019212479

2. ابعت سكرين التحويل للأدمن

3. ابعت رقم حسابك من زر 🆔 رقم حسابي

4. سيتم التفعيل خلال دقائق ✅"""


def _plans_text() -> str:
    return "\n".join(f"{key}: {label}" for key, label in PLAN_LABELS.items())
