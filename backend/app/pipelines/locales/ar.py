"""ما يقوله خط الأنابيب وعمليات تشغيله بالعربية (D226). المصطلحات تتبع معجم الشاشات."""

MESSAGES: dict[str, str] = {
    # تنفيذ تشغيل.
    "running its links": "تشغيل روابطه",
    "{name} is gone, or no longer shared with you": "{name} لم يعد موجودًا أو لم يعد مشتركًا معك",
    "{name} is switched off": "{name} مُعطّل",
    "{name} can no longer be opened": "{name} لم يعد يمكن فتحه",
    "You no longer have read access to {name}": "لم يعد لديك وصول القراءة إلى {name}",
    "You no longer have write access to {name}": "لم يعد لديك وصول الكتابة إلى {name}",
    "You no longer have structure access to {name}": "لم يعد لديك وصول إلى بنية {name}",
    "You no longer have own access to {name}": "لم تعد لديك صلاحية المالك على {name}",
    "The link could not run": "تعذّر تشغيل الرابط",
    "{link} made nothing in this run": "«{link}» لم ينشئ شيئًا في هذا التشغيل",
    "Its owner is no longer here": "مالكه لم يعد موجودًا",
    "{kind} is not possible between these connections": "«{kind}» غير ممكن بين هذه الاتصالات",
    "{kind} cannot run": "«{kind}» لا يمكن تشغيله",
    "The link it reads": "الرابط الذي يقرأه",
    "This run could not be read; nothing ran": "تعذّرت قراءة هذا التشغيل؛ لم يُشغَّل شيء",
    # جملة تشغيل.
    "{said}; {count} not run": "{said}؛ لم تُشغَّل: {count}",
    "{done} of {count} links ran": "شُغّل {done} من أصل {count} رابطًا",
    "Its one link ran": "شُغّل رابطه الوحيد",
    "All {count} links ran": "شُغّلت الروابط كلها: {count}",
    "Stopped at {at} of {count}, {title}: {reason}": "توقف عند {at} من {count}، «{title}»: {reason}",
    "Stopped at {at} of {count}, {title}": "توقف عند {at} من {count}، «{title}»",
    "Stopped on request at {at} of {count}, {title}": "توقف بناءً على طلب عند {at} من {count}، «{title}»",
    "Stopped on request before its first link": "توقف بناءً على طلب قبل رابطه الأول",
    "Stopped on request after {done} of {count}": "توقف بناءً على طلب بعد {done} من {count}",
    # بدء تشغيل.
    "{number} · {title} needs its table named and its columns chosen": "{number} · «{title}» يحتاج إلى تسمية جدوله واختيار أعمدته",
    "{number} · {title} needs its columns paired": "{number} · «{title}» يحتاج إلى مزاوجة أعمدته",
    "a result": "نتيجة",
    "{connection} (top)": "{connection} (الأعلى)",
    "Nothing ran: {needs}": "لم يُشغَّل شيء: {needs}",
    # لوحة الرسم.
    "This connection is gone, or no longer shared with you": "هذا الاتصال لم يعد موجودًا أو لم يعد مشتركًا معك",
    "This connection is switched off": "هذا الاتصال مُعطّل",
    "This connection cannot be read": "تعذّرت قراءة هذا الاتصال",
    "{names} and {last}": "{names} و{last}",
    "{names} write into each other, so the arrows give no first link: this one goes first because its card is furthest left": "{names} يكتب كل منها في الآخر، لذا لا تحدد الأسهم الرابط الأول: يبدأ هذا أولًا لأن بطاقته في أقصى اليسار",
    "{names} write into each other, so the arrows give no first link: this one goes first because its card is highest": "{names} يكتب كل منها في الآخر، لذا لا تحدد الأسهم الرابط الأول: يبدأ هذا أولًا لأن بطاقته في الأعلى",
    "{names} write into each other, so the arrows give no first link: this one goes first because it starts from the highest row": "{names} يكتب كل منها في الآخر، لذا لا تحدد الأسهم الرابط الأول: يبدأ هذا أولًا لأنه ينطلق من أعلى صف",
    "{names} write into each other, so the arrows give no first link: this one goes first because it was drawn first": "{names} يكتب كل منها في الآخر، لذا لا تحدد الأسهم الرابط الأول: يبدأ هذا أولًا لأنه رُسم أولًا",
    "{names} write into each other, so the arrows give no first link: this one goes first because the others wait for links outside them as well": "{names} يكتب كل منها في الآخر، لذا لا تحدد الأسهم الرابط الأول: يبدأ هذا أولًا لأن الآخرين ينتظرون روابط خارجها أيضًا",
    "{name} was removed": "أُزيل {name}",
    # البحث.
    "Pipelines": "خطوط الأنابيب",
    "Pipeline": "خط أنابيب",
    # A link keeping the latest per key (D314).
    "{number} · {title} needs its key and values chosen": "{number} · «{title}» يحتاج إلى اختيار مفتاحه وقيمه",
    # A pipeline following its topics (D315).
    "Followed; {count} messages carried": "تمت المتابعة؛ الرسائل المنقولة: {count}",
    "Only a link reading a topic follows it": "لا يتابع الموضوع إلا رابط يقرؤه",
    "This following could not be read": "تعذّرت قراءة هذه المتابعة",
    "following its topics": "يتابع مواضيعه",
    # A pipeline switched on with one button (D362, D363).
    "Runs continuously; not run": "يعمل باستمرار؛ لم يُشغَّل",
    "Not switched on: {needs}": "لم يُشغَّل: {needs}",
    "Same connection": "الاتصال نفسه",
    "Nothing can go from here into this connection": "لا يمكن نقل شيء من هنا إلى هذا الاتصال",
    "Already linked": "مرتبط بالفعل",
    "Nothing can go here": "لا يمكن نقل شيء إلى هنا",
}
