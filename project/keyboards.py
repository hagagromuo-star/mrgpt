from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from config import SUBJECTS


BTN_EXPLAIN = "📚 شرح درس"
BTN_SUMMARY = "📝 تلخيص درس"
BTN_LESSON_QUIZ = "🧪 امتحان على درس"
BTN_FULL_EXAM = "📖 امتحان على المنهج كامل"
BTN_STUDY_PLAN = "🗓️ خطة مذاكرة"
BTN_DAILY_VIP = "⭐ VIP يومي"
BTN_SUBSCRIBE = "💳 الاشتراك"
BTN_ACCOUNT_ID = "🆔 رقم حسابي"
BTN_CONTACT_ADMIN = "📞 تواصل مع الأدمن"

BTN_ADMIN_ACTIVATE = "✅ تفعيل اشتراك"
BTN_ADMIN_DEACTIVATE = "❌ إلغاء اشتراك"
BTN_ADMIN_STATUS = "🔍 حالة مستخدم"
BTN_ADMIN_BROADCAST = "📢 رسالة جماعية"
BTN_ADMIN_SEND_VIP = "⭐ إرسال VIP"
BTN_ADMIN_STATS = "📊 الإحصائيات"

DIFFICULTIES = {"سهل", "متوسط", "صعب"}
ANSWER_LABELS = ["أ", "ب", "ج", "د"]


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_EXPLAIN), KeyboardButton(text=BTN_SUMMARY)],
            [KeyboardButton(text=BTN_LESSON_QUIZ), KeyboardButton(text=BTN_FULL_EXAM)],
            [KeyboardButton(text=BTN_STUDY_PLAN), KeyboardButton(text=BTN_DAILY_VIP)],
            [KeyboardButton(text=BTN_SUBSCRIBE), KeyboardButton(text=BTN_ACCOUNT_ID)],
            [KeyboardButton(text=BTN_CONTACT_ADMIN)],
        ],
        resize_keyboard=True,
        input_field_placeholder="اختار اللي محتاجه يا بطل",
    )


def subjects_keyboard() -> ReplyKeyboardMarkup:
    labels = [value["label"] for value in SUBJECTS.values()]
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=labels[0]), KeyboardButton(text=labels[1])],
            [KeyboardButton(text=labels[2]), KeyboardButton(text=labels[3])],
            [KeyboardButton(text=labels[4])],
        ],
        resize_keyboard=True,
        input_field_placeholder="اختار المادة",
    )


def difficulty_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="سهل"), KeyboardButton(text="متوسط"), KeyboardButton(text="صعب")],
        ],
        resize_keyboard=True,
        input_field_placeholder="اختار الصعوبة",
    )


def answer_keyboard(question_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=label, callback_data=f"answer:{question_index}:{idx}")
                for idx, label in enumerate(ANSWER_LABELS)
            ]
        ]
    )


def admin_panel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADMIN_ACTIVATE), KeyboardButton(text=BTN_ADMIN_DEACTIVATE)],
            [KeyboardButton(text=BTN_ADMIN_STATUS), KeyboardButton(text=BTN_ADMIN_BROADCAST)],
            [KeyboardButton(text=BTN_ADMIN_SEND_VIP), KeyboardButton(text=BTN_ADMIN_STATS)],
        ],
        resize_keyboard=True,
        input_field_placeholder="اختار أمر الأدمن",
    )
