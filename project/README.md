# مستر المراجعة

بوت Telegram تعليمي لطلاب الصف الثالث الإعدادي في مصر. البوت بيشرح الدروس، يلخصها، يعمل امتحانات، يجهز خطط مذاكرة، ويدعم VIP يومي باستخدام ملفات PDF الخاصة بالمنهج و OpenAI.

## المتطلبات

- Python 3.11 أو أحدث
- Telegram Bot Token
- OpenAI API Key
- ملفات PDF للمنهج داخل مجلد `data/`

## إنشاء بوت من BotFather

1. افتح Telegram وابحث عن `@BotFather`.
2. اكتب `/newbot`.
3. اكتب اسم البوت: `مستر المراجعة`.
4. اختار username للبوت ينتهي بـ `bot`.
5. BotFather هيديك `BOT_TOKEN`.

## الحصول على OpenAI API Key

1. افتح حسابك على منصة OpenAI.
2. ادخل على صفحة API Keys.
3. أنشئ مفتاح جديد.
4. احتفظ بالمفتاح لاستخدامه في ملف `.env` أو Render Environment Variables.

## الحصول على Telegram ID

1. افتح Telegram وابحث عن `@userinfobot`.
2. اضغط Start.
3. خد رقم `Id` وحطه في `ADMIN_IDS`.
4. لو عندك أكتر من أدمن، افصل الأرقام بفاصلة: `123,456`.

## إعداد البيئة

انسخ ملف `.env.example` إلى `.env` داخل مجلد المشروع، ثم عدل القيم:

```env
BOT_TOKEN=YOUR_BOT_TOKEN
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
ADMIN_IDS=123456789
```

## تشغيل المشروع محليًا

نفذ الأوامر من داخل مجلد `project`:

```bash
pip install -r requirements.txt
python bot.py
```

## رفع ملفات PDF

ضع ملفات المنهج داخل مجلد `data/` بنفس الأسماء التالية:

- `arabic.pdf` لمادة عربي
- `english.pdf` لمادة إنجليزي
- `math.pdf` لمادة رياضيات
- `science.pdf` لمادة علوم
- `studies.pdf` لمادة دراسات

مهم: استبدل ملفات PDF المكانية الموجودة بملفات المنهج الحقيقية قبل تشغيل البوت للطلاب.

## تشغيله على GitHub و Render

1. ارفع مجلد المشروع على GitHub.
2. افتح Render واعمل New Worker.
3. اربط المستودع من GitHub.
4. اختار Python Environment.
5. Build Command:

```bash
pip install -r requirements.txt
```

6. Start Command:

```bash
python bot.py
```

7. من Environment Variables أضف:

- `BOT_TOKEN`
- `OPENAI_API_KEY`
- `ADMIN_IDS`

8. لو هتستخدم `render.yaml` الموجود، Render يقدر يقرأ إعدادات Worker تلقائيًا.

## أوامر الأدمن

- `/admin` يعرض أوامر الأدمن.
- `/admin_panel` يفتح لوحة الأدمن بالأزرار.
- `/activate user_id plan days` يفعل اشتراك.
- `/deactivate user_id` يلغي اشتراك.
- `/status user_id` يعرض حالة مستخدم.
- `/broadcast الرسالة هنا` يرسل رسالة لكل المستخدمين.
- `/send_vip المحتوى هنا` يرسل رسالة لمشتركي VIP.
- `/stats` يعرض الإحصائيات.

## الباقات

- `arabic` مادة عربي
- `english` مادة إنجليزي
- `math` مادة رياضيات
- `science` مادة علوم
- `studies` مادة دراسات
- `all` كل المواد
- `vip` VIP كامل

## نظام الاستخدام المجاني

كل مستخدم له 3 استخدامات مجانية يوميًا. بعد كده البوت يطلب الاشتراك من زر `💳 الاشتراك`.

## ملاحظات تشغيل مهمة

- البوت يستخدم SQLite في ملف `bot.db` ويتعمل تلقائيًا عند التشغيل.
- الكاش بيتخزن داخل مجلد `cache/` بصيغة JSON لتقليل تكلفة OpenAI.
- البحث في PDF مرن وبيحاول يلاقي الدرس حتى لو الطالب كتب الاسم بشكل قريب.
- لو الدرس مش موجود، البوت هيرد: `مش لاقي الدرس ده حاليًا 😅`.
