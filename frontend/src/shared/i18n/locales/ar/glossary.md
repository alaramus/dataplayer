# Arabic: terms and style

One word for one thing, across every screen. Add a term here before using a
second word for it.

## Style

- Modern Standard Arabic (`ar`), Quasar's `ar` pack, ECharts' `AR` pack. The
  page reads right to left: `applyLanguage` puts `dir="rtl"` on the document
  for Arabic (D281).
- Write a natural, modern Arabic interface. A label is short and noun-like:
  «حفظ»، «إلغاء»، «حذف»، «فتح». A button or menu item is an action, usually a
  verbal noun; an imperative is fine where it is the shorter word.
- Address the reader in the second person singular only where a full sentence
  must address one person: «لم يتم حفظ الملف». Otherwise prefer impersonal
  forms: «تعذّر حفظ الملف» / «لا يمكن الحفظ».
- Do not use diacritics except where a word is ambiguous without them
  (مؤقتًا، مُولَّد، عيّنة).
- Punctuation: «،» for a comma, «؛» for a semicolon, «؟» for a question mark,
  «:» for a colon. Quotes are «» or "". A dash is «-», an ellipsis is «…».
- Latin names and the Arabic sentence around them: keep one space between
  them, e.g. «اتصال PostgreSQL»، «ملف CSV»، «{n} صفوف». Never put an Arabic
  letter directly against a Latin one.
- Digits are the Western ones (0-9) everywhere, as in the data itself.
- Names a person typed (a table, a connection) stay as they are, in quotes.
- Product and protocol names stay in Latin: PostgreSQL, TimescaleDB, MySQL,
  MariaDB, SQLite, ClickHouse, Redis, SSH, SFTP, S3, SQL, CSV, JSON, DuckDB,
  Docker, ECharts.
- Do not translate code, identifiers, SQL, key names, enum values, or a
  `{placeholder}`. A placeholder is kept exactly: `{name}`, `{count}`,
  `{table}`. Never add, remove, rename or reorder its braces. A message's `|`
  plural forms are in the order `zero | one | two | few | many | other`; keep
  all six where the English has forms and a noun follows a number, so that
  3-10 and 11-99 read correctly.
- Never write a bare `@` or `$` in a vue-i18n message.
- A user's guide bullet must stay under 80 characters, as the panel beside the
  catalog shows one line per item.

## Terms

| English | العربية |
| --- | --- |
| connection | اتصال |
| source | مصدر |
| workspace | مساحة العمل |
| catalog | الكتالوج |
| node | عقدة |
| panel | لوحة |
| tab | تبويب |
| tab group | مجموعة تبويبات |
| rail (tool rail) | شريط الأدوات |
| bottom panel | اللوحة السفلية |
| pair (two catalogs side by side) | زوج الكتالوجات |
| window | نافذة |
| table | جدول |
| view | عرض |
| materialized view | عرض مادي |
| relation | علاقة |
| schema | مخطط |
| database | قاعدة بيانات |
| column | عمود |
| row | صف |
| index | فهرس |
| constraint | قيد |
| primary key | المفتاح الأساسي |
| foreign key | المفتاح الأجنبي |
| reference (declared) | مرجع |
| declared reference | مرجع معلن |
| function | دالة |
| sequence | تسلسل |
| trigger | مشغّل |
| extension | امتداد |
| hypertable | جدول فائق |
| chunk | قطعة |
| key (Redis) | مفتاح |
| key space | فضاء المفاتيح |
| file storage | تخزين الملفات |
| bucket | حاوية |
| folder | مجلد |
| query | استعلام |
| query document | مستند استعلام |
| result | نتيجة |
| row view | عرض الصف |
| action | إجراء |
| capability | قدرة |
| preview | معاينة |
| download | تنزيل |
| export | تصدير |
| import | استيراد |
| paste | لصق |
| copy | نسخ |
| transfer | نقل |
| pipeline | خط أنابيب |
| link (pipeline) | رابط |
| run | تشغيل |
| job | مهمة |
| step | خطوة |
| dashboard | لوحة معلومات |
| widget | أداة |
| metric | مقياس |
| agent | وكيل |
| chat | دردشة |
| conversation | محادثة |
| message | رسالة |
| prompt | موجّه |
| model | نموذج |
| provider | مزوّد |
| search | بحث |
| search index | فهرس البحث |
| share | مشاركة |
| link (share) | رابط |
| access | وصول |
| grant | منح |
| user | مستخدم |
| account | حساب |
| superuser | مستخدم فائق |
| preference | تفضيل |
| theme | سمة |
| terminal | طرفية |
| server | خادم |
| service | خدمة |
| template | قالب |
| backup | نسخة احتياطية |
| report | تقرير |
| notification | إشعار |
| onboarding | البدء |
| guide | دليل |
| freshness | حداثة |
| grid | شبكة |
| record | سجل |
| content | محتوى |
| document | مستند |
| archive | أرشيف |
| relationship | ارتباط |
| schema form | نموذج المخطط |
| source operation | عملية مصدر |
| refresh | تحديث |
| reload | إعادة تحميل |
| save | حفظ |
| delete | حذف |
| cancel | إلغاء |
| close | إغلاق |
| open | فتح |
| settings | إعدادات |
| preferences | التفضيلات |
| clear | مسح |
| confirm | تأكيد |
| discard | إهمال |
| dismiss | تجاهل |
| fullscreen | ملء الشاشة |
| paused | متوقف مؤقتًا |
| chart | رسم بياني |
| diagram | رسم تخطيطي |
| callout | تنبيه |
| code block | كتلة تعليمات برمجية |
| project (agent) | مشروع |
| API key | مفتاح API |
| thinking | التفكير |
| pin / unpin | تثبيت / إلغاء التثبيت |
| archive (verb) | أرشفة |
| dictate | إملاء |
| quick chat | دردشة سريعة |
| attach | إرفاق |
| metrics store | مخزن المقاييس |
| sample | عيّنة |
| series | سلسلة |
| host | مضيف |
| preset | إعداد مسبق |
| range (of time) | نطاق |
| statement (SQL) | عبارة |
| transaction | معاملة |
| commit / roll back | تثبيت / تراجع |
| auto-commit | تثبيت تلقائي |
| explain (plan) | شرح |
| history | المحفوظات |
| favorites | المفضلة |
| draft | مسودة |
| console | وحدة تحكم |
| parameter | معامل |
| session | جلسة |
| view (of the grid) | عرض |
| auto-refresh | تحديث تلقائي |
| ascending / descending | تصاعدي / تنازلي |
| passphrase | عبارة مرور |
| public / private key | مفتاح عام / مفتاح خاص |
| lock / unlock (a key) | قفل / فتح القفل |
| server key | مفتاح الخادم |
| card (pipeline) | بطاقة |
| canvas | لوحة الرسم |
| restore | استعادة |
| output / logs | المخرجات / السجلات |
| container | حاوية |
| connection string | سلسلة الاتصال |
| generated column | عمود مُولَّد |
| tablespace | مساحة جدول |
| partition | قسم |
| collation | ترتيب المحارف |
| operator class | صنف المعامل |
| access method | طريقة الوصول |
| columnstore | مخزن الأعمدة |
| retention | الاحتفاظ |
| minimize / maximize | تصغير / تكبير |
| default server | الخادم الافتراضي |
| shell | صدفة |
| give / take away access | منح / سحب الوصول |
| request access | طلب الوصول |
| listen (read aloud) | استماع |
| tour | جولة |
| arrange (a graph) | ترتيب |
| zoom in / out | تكبير / تصغير |
| activity | النشاط |
| needs you | يحتاج إليك |
| working (running now) | قيد التشغيل |
| recent | الأخيرة |
| do not disturb | عدم الإزعاج |
| by meaning | بالمعنى |
| passage | مقطع |
| viewer | عارض |
| cut | قص |
| plan (of an operation) | خطة |
| destination | الوجهة |
| details | التفاصيل |
| layout (of tabs) | التخطيط |
| live (fresh data) | مباشر |
| section (of the panel engine) | قسم |
| put aside / bring back | إبعاد / إرجاع |
| owner | المالك |
| match (search) | تطابق |
| item / member | عنصر |
| stream entry | مدخل |
| live search | البحث المباشر |
| kept (a list read ahead) | محفوظ |

## Gender and number

- A sentence around a parameter must not depend on the parameter's gender or
  number: «{what}: تعذّر الحفظ», not «{what} فشل».
- After a counted noun use the plural forms in the order `zero | one | two |
  few | many | other`: `لا صفوف | صف واحد | صفان | {n} صفوف | {n} صفًا | {n} صف`.
  When a message has fewer forms, keep at least `one | other` and make the
  `other` form the one that reads correctly for 11 and above.
