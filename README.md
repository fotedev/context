# File Aggregator - دليل الاستخدام المتكامل

أداة متقدمة لجمع محتويات الملفات البرمجية وقصاصات الكود (Code Snippets)، وإنشاء خريطة لهيكل المشروع، ومقارنة مخرجات نماذج الذكاء الاصطناعي المختلفة تلقائياً باستخدام حَكَم ذكي. تم تصميم الأداة لتكون رفيقك المثالي عند استخدام منصات مثل **LMArena**.

---

## 🚀 الميزات الأساسية الحالية (Core Features)

### 🤖 1. نظام الحكم الذكي (Gemini AI Judge Mode)
تم دمج نموذج **Gemini Flash API** ليعمل كـ "حَكَم ومقيّم مستقل" لمخرجات النماذج:
- **التقييم التلقائي:** يقوم النموذج بفحص ومقارنة الإجابات الملتصقة في ملف `compare.md`.
- **تحديد الفائز:** يحلل الكود بدقة من حيث (الكفاءة، الحماية، البنية) ويكتب بوضوح **النموذج الفائز** مع ذكر الأسباب الفنية في ثوانٍ.

### 📊 2. عداد التوكنز الذكي (Token Counter)
- تقوم الأداة بحساب إجمالي عدد التوكنز (Tokens) لملف الـ Context المجمع قبل إرساله.
- تعتمد على مكتبة `tiktoken` لدقة متناهية، مع نظام تقدير ذكي (Fallback) في حال عدم تثبيتها، لتنبيهك بحجم البيانات وتجنب تخطي حدود النماذج (Rate Limits).

### ✂️ 3. الدعم المتقدم لقصاصات الكود (Code Snippets & Structures)
الأداة لا تقتصر على جمع الملفات الكاملة فحسب، بل تدعم تحديد أجزاء دقيقة من الكود لتوفير التوكنز عبر ملفات `.context/inputs/`:
- **Code Snippets:** جمع أسطر محددة (مثال: `/path/to/file.py:10-20`).
- **Multi-range Snippets:** جمع عدة أجزاء من نفس الملف مفصولة بـ `...` (مثال: `/path/to/file.py:10-20,50-60`).
- **Important Structures:** تمييز أجزاء الكود الهيكلية مثل الـ Types والـ Interfaces بإضافة علامة التعجب (مثال: `!/path/to/types.ts:1-15`).

### 📁 4. هيكل المخرجات المنظم (Arena-Based Output)
- تُنشأ مجلدات `arenas/` منظمة تحت `context_output/` لكل ملف إدخال.
- كل مجلد يحمل الصيغة `NNN-<اسم-الملف>/` (مثال: `001-fix-navbar-bug/`).
- لا تتم الكتابة فوق المجلدات القائمة — يتم الترقيم التلقائي دائمًا.

---

## 📂 بنية المشروع البرمجية (Project Architecture)
تم تقسيم الكود المصدري للأداة إلى وحدات منفصلة (Modules) لسهولة التطوير، الصيانة، وفصل المسؤوليات:

```text
context/
├── aggregator.py          # المدخل الرئيسي للأداة (CLI) ومسؤول عن التوجيه
├── core/
│   ├── __init__.py
│   ├── parser.py          # فحص الملفات، استخراج الكود، التعامل مع .contextignore وقصاصات الكود
│   ├── counter.py         # حساب عدد التوكنز (Token Counter) بدقة
│   └── judge.py           # الربط مع Gemini Flash API لإصدار الحكم والتقييم
├── aggregator_tui.py      # واجهة التيرمينال التفاعلية (TUI)
├── aggregator_gui.py      # الواجهة الرسومية (GUI)
└── .context/
    ├── settings.json      # إعدادات مستمرة
    ├── ignore             # أنماط التجاهل المخصصة
    └── inputs/            # ملفات الإدخال (موقع الاكتشاف الرئيسي)
```

---

## 💻 الواجهات المتاحة (Available Interfaces)

يمكنك تشغيل الأداة بأربع طرق مختلفة من التيرمينال:

| الأمر (Alias) | نوع الواجهة | الاستخدام المثالي |
| :--- | :--- | :--- |
| **`agg`** | **CLI** (Direct) | التشغيل المباشر من `files.txt` مع البحث التلقائي عن جذر المشروع. |
| **`aggf`** | **CLI** (Current) | تشغيل السكربت مع اعتبار **المجلد الحالي** هو الجذر (Root). |
| **`aggt`** | **TUI** (Terminal UI) | التصفح التفاعلي واختيار الملفات داخل التيرمينال (خفيف جداً). |
| **`aggg`** | **GUI** (Window) | واجهة نافذة كلاسيكية (Tkinter) بنظام Dark Mode. |

---

## ⚔️ ميزة مقارنة النماذج والتقييم (LMArena & Judge Mode)

عند تشغيل `agg` أو `aggf` من التيرمينال، سيسألك السكربت بشكل تفاعلي إذا كنت تريد إنشاء ملف مقارنة:
- **`compare.md`**: قالب منظم يحتوي على الـ Prompt، إجابات النماذج (من مجلد `models/` أو ملف `llm.txt`)، متبوعاً بـ **تقرير التقييم النهائي والحكم الصادر من Gemini Flash**.
- **Compact Mode**: خيار لتقليل عدد التوكنز في ملف المقارنة عبر إزالة المسافات الزائدة والملاحظات الفارغة.

---

## 🛠️ أوامر التيرمينال السريعة (CLI Commands)

بدلاً من فتح الملفات يدوياً، يمكنك إدارة قائمة الملفات بسرعة:

- **إضافة ملف للقائمة:** `agg-add filename.py`
- **عرض القائمة الحالية:** `agg-list`
- **تفريغ القائمة:** `agg-clear`
- **تشغيل التجميع المباشر:** `agg`

---

## 📤 المخرجات (Outputs)

بمجرد انتهاء التشغيل (بأي طريقة)، ستجد:
1. **`context_output/arenas/NNN-<name>/arena.txt`**: يحتوي على محتوى جميع الملفات والـ Snippets المجمعة مع فواصل واضحة وجاهزة للنسخ.
2. **`context_output/arenas/NNN-<name>/structure.txt`**: يحتوي على رسم شجري لهيكل المشروع بالكامل.
3. **`context_output/arenas/NNN-<name>/compare.md`**: سجل مقارنة النماذج مدعوماً بـ **التقرير التحليلي وإعلان الفائز بواسطة Gemini Judge**.

---

## ⚙️ التخصيص (Ignore Patterns)
لتجاهل ملفات أو مجلدات معينة، أنشئ ملف `.context/ignore` داخل مجلد `.context/` وأضف داخله الأنماط التي تريد تجاهلها (مثل `.git`, `node_modules`). الأداة تتجاهل تلقائياً الملفات غير الضرورية مثل `__pycache__` و `.next`.

**ملاحظة:** الأداة تدعم أيضًا ملفات `.contextignore` و `.index_ignore` للتوافق مع الإصدارات القديمة.

---

## 🔐 إعداد البيئة ومتغيرات النظام (Configuration)

لتفعيل ميزة الحكم التلقائي، يجب إضافة الـ API Key الخاص بـ Gemini في متغيرات البيئة (أو سيطلبه منك السكربت ويحفظه في ملف `.env`):

### في نظام Linux / WSL (`~/.zshrc` أو `~/.bashrc`):
```bash
export GEMINI_API_KEY="your_api_key_here"

alias agg='python3 /mnt/data/programming/Python/Projects/context/aggregator.py'
alias aggf='python3 /mnt/data/programming/Python/Projects/context/aggregator.py .'
alias aggt='/mnt/data/programming/Python/Projects/context/.venv/bin/python3 /mnt/data/programming/Python/Projects/context/aggregator_tui.py'
alias aggg='/mnt/data/programming/Python/Projects/context/.venv/bin/python3 /mnt/data/programming/Python/Projects/context/aggregator_gui.py'
```

### في نظام Windows (PowerShell Profile):
```powershell
$env:GEMINI_API_KEY="your_api_key_here"

function agg { python C:\programming\Python\Projects\context\aggregator.py $args }
function aggf { python C:\programming\Python\Projects\context\aggregator.py . $args }
function aggt { python C:\programming\Python\Projects\context\aggregator_tui.py $args }
function aggg { python C:\programming\Python\Projects\context\aggregator_gui.py $args }
```

---

## 🗺️ خطة الميزات المستقبلية (Roadmap)

نعمل باستمرار على تطوير الأداة لتصبح منصة متكاملة. إليك ما نخطط لإضافته قريباً:

* [ ] **حاسبة التكلفة التقديرية (Cost Estimator):** حساب تكلفة استهلاك التوكنز بناءً على أسعار APIs الرسمية (OpenAI, Anthropic, Google) قبل إرسال الطلبات لتجنب الصدمات.
* [ ] **وضع تخصيص الحكم (Custom Judge Personas):** إمكانية توجيه الحكم ليركز على جوانب معينة عبر تمرير Flags، (مثلاً: `--judge security` للتركيز على الثغرات، أو `--judge performance` لسرعة التنفيذ والـ Clean Code).
* [ ] **نظام التجميع المتزايد (Incremental Context):** تجميع الملفات التي جرى عليها تعديل في الـ Git فقط (Staged/Modified) لتوفير التوكنز بشكل كبير.
* [ ] **تصدير التقارير التفاعلية (Interactive HTML Report):** توليد صفحة HTML تفاعلية (Dark Mode) تتضمن أزرار للتنقل بين إجابات الموديلات و "Highlighter" للفروقات بين الأكواد (Code Diff Viewer).
