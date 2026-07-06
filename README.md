# File Aggregator - دليل الاستخدام المتكامل

أداة متقدمة لجمع محتويات الملفات البرمجية وقصاصات الكود (Code Snippets)، وإنشاء خريطة لهيكل المشروع، ومقارنة مخرجات نماذج الذكاء الاصطناعي المختلفة تلقائياً باستخدام حَكَم ذكي. تم تصميم الأداة لتكون رفيقك المثالي عند استخدام منصات مثل **LMArena**.

---

## الميزات الأساسية (Core Features)

### 1. نظام الحكم الذكي (Gemini AI Judge Mode)
تم دمج نموذج **Gemini Flash API** ليعمل كـ "حَكَم ومقيّم مستقل" لمخرجات النماذج:
- **التقييم التلقائي:** يقوم النموذج بفحص ومقارنة الإجابات الملتصقة في ملف `arena.{md,txt}`.
- **تحديد الفائز:** يحلل الكود بدقة من حيث (الكفاءة، الحماية، البنية) ويكتب بوضوح **النموذج الفائز** مع ذكر الأسباب الفنية.

### 2. عداد التوكنز الذكي (Token Counter)
- تقوم الأداة بحساب إجمالي عدد التوكنز (Tokens) لملف الـ Context المجمع قبل إرساله.
- تعتمد على مكتبة `tiktoken` لدقة متناهية، مع نظام تقدير ذكي (Fallback) في حال عدم تثبيتها.

### 3. الدعم المتقدم لقصاصات الكود (Code Snippets & Structures)
الأداة لا تقتصر على جمع الملفات الكاملة فحسب، بل تدعم تحديد أجزاء دقيقة من الكود عبر ملفات `.context/inputs/`:
- **Code Snippets:** جمع أسطر محددة (مثال: `/path/to/file.py:10-20`).
- **Multi-range Snippets:** جمع عدة أجزاء من نفس الملف مفصولة بـ `...` (مثال: `/path/to/file.py:10-20,50-60`).
- **Important Structures:** تمييز أجزاء الكود الهيكلية مثل الـ Types والـ Interfaces بإضافة علامة التعجب (مثال: `!/path/to/types.ts:1-15`).

### 4. هيكل المخرجات المنظم (Arena-Based Output)
- تُنشأ مجلدات `arenas/` منظمة تحت `context_output/` لكل ملف إدخال.
- كل مجلد يحمل الصيغة `NNN-<اسم-الملف>/` (مثال: `001-fix-navbar-bug/`).
- لا تتم الكتابة فوق المجلدات القائمة — يتم الترقيم التلقائي دائمًا.
- **البحث المتداخل**: يدعم البحث عن ملفات الإدخال بشكل تلقائي داخل المجلدات الفرعية داخل `.context/inputs/`.
- **تسمية ذكية**: يتم دمج مسار المجلدات الفرعية مع اسم الملف لتوليد اسم الـ Arena:
  - مثال: `.context/inputs/UI/AdminPage.txt` → `010-UI-AdminPage/`
- **الترقيم المُستهدف (Target Arena Directive)**: يمكنك تثبيت رقم الـ Arena عبر إضافة تعليق في أول سطر من ملف الإدخال:
  ```
  # Target Arena: 006-AdminDashboard
  ```

### 5. أرشفة النماذج (Model Archiving)
- يمكن أرشفة ردود النماذج في مجلد `ARCHIVE/` داخل كل Arena مع الحفاظ على القالب الأصلي.
- يتم التحكم عبر إعداد `archive` في `.context/settings.json`.

### 6. أرشفة المرفقات اللصقية (Paste Attachments)
- يمكن نسخ ملفات `.txt` من `tmp/paste-attachments/<تاريخ>/` إلى مجلد الإخراج تلقائياً مع تسمية ذكية مبنية على أول جملتين من محتوى الملف.
- يتم التحكم عبر إعداد `paste_attachments_enabled` في `.context/settings.json`.

---

## بنية المشروع البرمجية (Project Architecture)

تم تقسيم الكود المصدري للأداة إلى وحدات منفصلة (Modules) لسهولة التطوير والصيانة:

```text
context/
├── aggregator.py              # المدخل الرئيسي للأداة (CLI)
├── aggregator_tui.py          # واجهة التيرمينال التفاعلية (TUI) - تتطلب textual
├── aggregator_gui.py          # الواجهة الرسومية (GUI) - Tkinter
├── install.py                 # سكربت تثبيت المكتبات الاختيارية (tiktoken, textual)
├── renumber_arenas.py         # أداة ترحيل لإعادة ترقيم مجلدات الـ Arena
├── core/
│   ├── __init__.py            # تهيئة الحزمة
│   ├── parser.py              # تحليل المسارات، التجميع، الشجرة، إعادة التصدير
│   ├── arena.py               # تحليل تعليمات Target Arena، تخطيط الأرقام، حل التعارضات
│   ├── discovery.py           # اكتشاف الملفات، تطبيق أنماط التجاهل، لقطة الحالة
│   ├── settings.py            # إدارة الإعدادات، أرشفة المرفقات اللصقية
│   ├── counter.py             # حساب عدد التوكنز (tiktoken مع Fallback)
│   └── judge.py               # الربط مع Gemini Flash API لإصدار الحكم والتقييم
├── gui/
│   ├── browser-extension/     # (محفوظات - غير مستخدمة حالياً)
│   └── vscode-extension/      # (محفوظات - غير مستخدمة حالياً)
├── skills/
│   └── migrate-to-flat-layout/
│       └── migrate_inputs.py  # سكربت ترحيل
├── arena-context/
│   ├── SKILL.md               # مهارة سياق الـ Arena
│   └── organize-root.md       # مهارة تنظيم الجذر
├── .context/
│   ├── settings.json          # إعدادات مستمرة
│   ├── ignore                 # أنماط التجاهل المخصصة
│   ├── inputs/                # ملفات الإدخال (موقع الاكتشاف الرئيسي)
│   └── last_arena.json        # لقطة حالة Arena (تذكرة للـ AI agents)
├── .env                       # مفتاح Gemini API (في جذر الأداة)
├── .env.example               # قالب ملف .env
├── requirements.txt           # المتطلبات الاختيارية (tiktoken, textual)
└── context_output/            # مجلد المخرجات (يتم إنشاؤه تلقائياً)
    ├── arenas/                # مجلدات الـ Arena المنظمة
    │   └── NNN-<name>/        # مجلد واحد لكل إدخال
    │       ├── NNN-<name>.txt         # ملف الإدخال الأصلي (نسخة محفوظة)
    │       ├── NNN-context.{md,txt}   # محتوى الملفات المجمعة
    │       ├── NNN-arena.{md,txt}     # مقارنة النماذج
    │       ├── NNN-prompt.txt         # الـ Prompt المُرسل للنماذج
    │       ├── NNN-A.txt              # رد النموذج A
    │       ├── NNN-B.txt              # رد النموذج B
    │       └── ARCHIVE/               # الأرشيف (اختياري)
    ├── structure/
    │   └── structure.txt      # شجرة هيكل المشروع
    ├── models/                # مجلد النماذج المُرحّل (قديم)
    └── tmp/                   # ملفات مؤقتة
```

---

## الواجهات المتاحة (Available Interfaces)

يمكنك تشغيل الأداة بطرق مختلفة من التيرمينال:

| الأمر | نوع الواجهة | الاستخدام المثالي |
| :--- | :--- | :--- |
| **`agg`** | **CLI** (Direct) | التشغيل المباشر مع البحث التلقائي عن جذر المشروع. |
| **`aggf`** | **CLI** (Current) | تشغيل السكربت مع اعتبار **المجلد الحالي** هو الجذر (Root). |
| **`aggt`** | **TUI** (Terminal UI) | التصفح التفاعلي واختيار الملفات داخل التيرمينال (يتطلب `pip install textual`). |
| **`aggg`** | **GUI** (Window) | واجهة نافذة كلاسيكية (Tkinter) بنظام Dark Mode. |

---

## أوامر التيرمينال السريعة (CLI Commands)

```bash
# التشغيل الأساسي
agg                     # تشغيل مع البحث التلقائي عن الجذر
aggf                    # تشغيل مع الجذر الحالي
aggt                    # واجهة تفاعلية في التيرمينال (TUI)
aggg                    # واجهة رسومية (GUI)

# تعريف الأكواد في PowerShell Profile
function agg { python C:\path\to\context\aggregator.py $args }
function aggf { python C:\path\to\context\aggregator.py . $args }
function aggt { python C:\path\to\context\aggregator_tui.py $args }
function aggg { python C:\path\to\context\aggregator_gui.py $args }

# في Linux/WSL (أضف إلى ~/.bashrc أو ~/.zshrc)
alias agg='python3 /path/to/context/aggregator.py'
alias aggf='python3 /path/to/context/aggregator.py .'
alias aggt='python3 /path/to/context/aggregator_tui.py'
alias aggg='python3 /path/to/context/aggregator_gui.py'
```

### أعلام CLI (CLI Flags)

| العلم | التأثير |
| :--- | :--- |
| `--interactive` | عرض جميع الأسئلة التفاعلية (يتجاوز إعدادات settings.json) |
| `--output DIR` | تحديد مجلد الإخراج يدوياً (يتجاوز `output_dir` في الإعدادات) |
| `--status` | طباعة لقطة حالة المشروع للـ AI agents والخروج |
| `--json` | مع `--status`: إخراج JSON ل stdout (للبرمجة) |
| `-q`, `--quiet` | مع `--status`: طباعة رقم الـ Arena التالي فقط في سطر واحد |
| `--settings` | عرض مسار ملف الإعدادات ومحتواه والـ schema ثم الخروج |
| (بدون أعلام) | قراءة settings.json، اكتشاف ملفات الإدخال تلقائياً، التشغيل الصامت |

### تثبيت المكتبات الاختيارية

```bash
python install.py
```

هذا السكربت يُثبّت `tiktoken` (لدقة حساب التوكنز) و `textual` (لواجهة TUI). الأداة تعمل بدونها لكن بدقة أقل في العد.

---

## مقارنة النماذج والتقييم (LMArena & Judge Mode)

عند تشغيل `agg` أو `aggf` مع `--interactive`، سيسألك السكربت عن:
- **تشغيل Gemini Judge**: تلقائي أو يدوي
- **Compact Mode**: تقليل التوكنز عبر إزالة المسافات الزائدة
- **عدد النماذج**: 2 أو 4
- **صيغة الإخراج**: `.md` أو `.txt`

### هيكل ملفات الـ Arena (v3+ Flat Layout)

```
003-Hero/
├── 003-Hero.txt       ← ملف الإدخال الأصلي (نسخة محفوظة)
├── 003-context.md     ← محتوى الملفات المجمعة (السياق المُرسل للنماذج)
├── 003-arena.md       ← ملف مقارنة النماذج
├── 003-prompt.txt     ← الـ Prompt المُرسل
├── 003-A.txt          ← رد النموذج A
├── 003-B.txt          ← رد النموذج B
└── ARCHIVE/           ← أرشيف ردود النماذج (اختياري)
```

**ملاحظة**: كل ملف يحمل بادئة `NNN-` مطابقة لاسم المجلد لتجنب التداخل عند فتح عدة Arenas. الملفات القديمة بدون بادئة (من تخطيط v2) تُخفي تلقائياً من `structure.txt` وشجرة المشروع عبر قاعدة هيكلية في `should_ignore()`.

### تنظيف الملفات القديمة (Phase 3 Migration)

يتم تنظيف الملفات القديمة غير المُسبقة تلقائياً أثناء كل تشغيل:
- **إعادة تسمية**: الملفات بدون بادئة تُعاد تسميتها بالبادئة الصحيحة (مثال: `arena.txt` → `003-arena.md`)
- **إزالة المكررات**: إذا كانت نسختان (مسبقة وغير مسبقة) متماثلتان، تُحذف النسخة غير المسبقة
- **تحذير عند الاختلاف**: إذا اختلف المحتوى، تُ keeping两者 ويتم طلب مراجعة يدوية

---

## تعليمات الـ Arena المُستهدفة (Target Arena Directive)

يمكنك تثبيت رقم الـ Arena عبر إضافة تعليق في أول سطر غير فارغ من ملف الإدخال:

```txt
# Target Arena: 006-AdminDashboard
/path/to/component.tsx
/path/to/styles.css:10-30
```

- إذا حدث تعارض بين رقمين متساويين، سيتم تحذيرك ونقل أحدهما للرقم التالي المتاح.
- اسم الملف يظل المصدر الحاسم لاسم الـ Arena (وليست التعليق).
- يمكن تعطيل هذه الميزة عبر `respect_target_arena_directive: false` في الإعدادات.

---

## المخرجات (Outputs)

بمجرد انتهاء التشغيل، ستجد:

1. **`context_output/arenas/NNN-<name>/NNN-context.{md,txt}`**: محتوى جميع الملفات والـ Snippets المجمعة.
2. **`context_output/structure/structure.txt`**: شجرة هيكل المشروع بالكامل.
3. **`context_output/arenas/NNN-<name>/NNN-arena.{md,txt}`**: ملف مقارنة النماذج مع **التقرير التحليلي وإعلان الفائز بواسطة Gemini Judge**.

### لقطة الحالة (State Breadcrumb)

يتم كتابة `context_output/.context/last_arena.json` تلقائياً في نهاية كل تشغيل. يحتوي على:
- رقم آخر Arena ورقم التالي
- إجمالي عدد الـ Arenas
- آخر نشاط والوقت
- عدد ملفات الإدخال

يمكن استخدام `agg --status` لعرض هذه المعلومات مباشرة.

---

## التخصيص (Ignore Patterns)

لتجاهل ملفات أو مجلدات معينة، أنشئ ملف `.context/ignore` داخل مجلد `.context/` وأضف داخله الأنماط التي تريد تجاهلها.

### الأنماط الافتراضية

الأداة تتجاهل تلقائياً:
- `.git`, `node_modules`, `venv`, `.venv`
- `.vscode`, `.idea`, `.cursor`, `.windsurf`
- `__pycache__`, `*.pyc`, `dist`, `build`, `.next`
- `context_output`, `.context`, `files.txt`, `models/`
- الملفات القديمة غير المُسبقة داخل مجلدات الـ Arena (مثل `A.txt`, `arena.md`, `context.md`, `prompt.txt`)

**ملاحظة**: الملفات القديمة تُخفي أيضاً عبر قاعدة هيكلية مستقلة في `should_ignore()` حتى عند تعطيل `use_default_ignore`.

### تعطيل الأنماط الافتراضية

لتعطيل الأنماط الافتراضية والتحكم الكامل في ملف `ignore`:

```json
// .context/settings.json
{
  "use_default_ignore": false
}
```

عند التعطيل، لن يتم إنشاء أو تعديل ملف `.context/ignore` تلقائياً.

---

## الإعدادات (Configuration)

### ملف الإعدادات

`.context/settings.json` — يتم إنشاؤه تلقائياً في أول تشغيل:

```json
{
  "output_dir": "context_output",
  "output_format": "md",
  "model_count": 2,
  "gemini_judge": false,
  "compact_mode": false,
  "archive": false,
  "archive_dir": "ARCHIVE",
  "paste_attachments_enabled": false,
  "paste_attachments_source_dir": "tmp/paste-attachments",
  "paste_attachments_target_subdir": "tmp/paste-attachments",
  "paste_attachments_date_format": "%Y-%m-%d",
  "paste_attachments_copy_mode": "copy",
  "respect_target_arena_directive": true,
  "target_arena_directive_prefix": "# Target Arena:",
  "on_arena_number_conflict": "warn_and_shift",
  "use_default_ignore": true
}
```

| المفتاح | القيمة الافتراضية | الوصف |
| :--- | :--- | :--- |
| `output_dir` | `"context_output"` | مجلد الإخراج الرئيسي |
| `output_format` | `"md"` | صيغة الملفات: `"md"` أو `"txt"` |
| `model_count` | `2` | عدد ملفات الردود (2 أو 4) |
| `gemini_judge` | `false` | تفعيل الحكم التلقائي |
| `compact_mode` | `false` | تقليل التوكنز في ملف المقارنة |
| `archive` | `false` | أرشفة ردود النماذج بعد كل تشغيل |
| `archive_dir` | `"ARCHIVE"` | مجلد الأرشيف داخل كل Arena |
| `paste_attachments_enabled` | `false` | تفعيل أرشفة المرفقات اللصقية |
| `use_default_ignore` | `true` | استخدام الأنماط الافتراضية في `ignore` |
| `respect_target_arena_directive` | `true` | احترام تعليمات `# Target Arena:` |
| `on_arena_number_conflict` | `"warn_and_shift"` | سلوك التعارض: `"warn_and_shift"`, `"fail"`, أو `"silent"` |

### متغيرات البيئة (Environment Variables)

لتفعيل ميزة الحكم التلقائي، يجب إضافة الـ API Key الخاص بـ Gemini:

**في نظام Linux / WSL (`~/.bashrc` أو `~/.zshrc`):**
```bash
export GEMINI_API_KEY="your_api_key_here"
```

**في نظام Windows (PowerShell Profile):**
```powershell
$env:GEMINI_API_KEY="your_api_key_here"
```

**أو** أنشئ ملف `.env` في جذر الأداة (حيث `aggregator.py`):
```
GEMINI_API_KEY=your_api_key_here
```

### ترتيب الأولوية (Configuration Precedence)

```
Command Line Flags > Interactive Prompts > settings.json > Defaults
```

---

## أدوات مساعدة (Utility Scripts)

### إعادة ترقيم Arenas

```bash
python renumber_arenas.py              # عرض الخطة فقط (dry-run)
python renumber_arenas.py --apply      # تنفيذ إعادة التسمية
python renumber_arenas.py --apply --force  # إعادة التسمية حتى مع المحتوى
```

أداة لإعادة ترتيب أرقام مجلدات الـ Arena بناءً على تعليمات `# Target Arena:` في ملفات الإدخال.

### تثبيت المكتبات

```bash
python install.py
```

يُثبّت `tiktoken` و `textual` — المكتبات الاختيارية لدقة العد وواجهة TUI.

---

## خطة الميزات المستقبلية (Roadmap)

نعمل باستمرار على تطوير الأداة. إليك ما نخطط لإضافته:

* [ ] **حاسبة التكلفة التقديرية (Cost Estimator):** حساب تكلفة استهلاك التوكنز بناءً على أسعار APIs الرسمية قبل إرسال الطلبات.
* [ ] **وضع تخصيص الحكم (Custom Judge Personas):** إمكانية توجيه الحكم للتركيز على جوانب معينة عبر `--judge security` أو `--judge performance`.
* [ ] **نظام التجميع المتزايد (Incremental Context):** تجميع الملفات المُعدّلة في Git فقط لتوفير التوكنز.
* [ ] **تصدير التقارير التفاعلية (Interactive HTML Report):** صفحة HTML تفاعلية بـ Dark Mode مع Code Diff Viewer.
* [ ] **واجهة سيرفر ويب (Web Server Interface):** سيرفر محلي بواجهة تحكم في المتصفح.
