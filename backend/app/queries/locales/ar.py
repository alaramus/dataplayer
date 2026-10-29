"""ما يقوله تشغيل الاستعلامات بالعربية (D226). المصطلحات تتبع معجم الشاشات."""

MESSAGES: dict[str, str] = {
    # قبل التشغيل.
    "There is nothing to run": "لا يوجد ما يُنفَّذ",
    "This is more than one statement; run it as a script to run them all": "هذه أكثر من عبارة واحدة؛ نفّذها كسكربت لتنفيذها كلها",
    "A script may hold at most {count} statements": "يمكن أن يحتوي السكربت على {count} عبارة كحد أقصى",
    "Statement {at} is larger than one statement may be": "العبارة {at} أكبر من الحجم المسموح لعبارة واحدة",
    "Statement {at}: {refusal}": "العبارة {at}: {refusal}",
    "Maintenance commands run outside a transaction; turn the manual transaction off to run this": "أوامر الصيانة تُنفَّذ خارج معاملة؛ أوقف المعاملة اليدوية لتنفيذ هذا",
    "A maintenance command runs outside a transaction, so run it on its own": "أمر الصيانة يُنفَّذ خارج معاملة، فنفّذه على حدة",
    "Statement {at} is a {kind} statement, and this run is a read": "العبارة {at} عبارة {kind}، وهذا التشغيل قراءة",
    "Statement {at} is a {kind} statement, and statements of that kind are not run here": "العبارة {at} عبارة {kind}، وعبارات هذا النوع لا تُنفَّذ هنا",
    "No value was given for {names}": "لم تُعطَ قيمة لـ {names}",
    # الكتابة.
    "A write cannot run in read mode": "لا يمكن تنفيذ كتابة في نمط القراءة",
    "The owner of this connection allows reading only": "مالك هذا الاتصال يسمح بالقراءة فقط",
    "A {kind} statement needs read access to this connection": "عبارة {kind} تحتاج إلى وصول القراءة إلى هذا الاتصال",
    "A {kind} statement needs write access to this connection": "عبارة {kind} تحتاج إلى وصول الكتابة إلى هذا الاتصال",
    "A {kind} statement needs structure access to this connection": "عبارة {kind} تحتاج إلى وصول إلى بنية هذا الاتصال",
    "A {kind} statement needs own access to this connection": "عبارة {kind} تحتاج إلى صلاحية المالك على هذا الاتصال",
    "Confirm this write before running it": "أكّد هذه الكتابة قبل تنفيذها",
    "This run asks for something that cannot be undone; confirm it first": "يطلب هذا التشغيل شيئًا لا يمكن التراجع عنه؛ أكّده أولًا",
    "You have read access to this connection": "لديك وصول القراءة إلى هذا الاتصال",
    # تشغيل.
    "This run could not be completed": "تعذّر إكمال هذا التشغيل",
    "There was no room to keep this result": "لم تكن هناك مساحة لحفظ هذه النتيجة",
    # المعاملات والمحفوظات.
    "Committed {count} changing statement, {rows} rows": "تم تثبيت {count} عبارة مبدّلة للبيانات، {rows} صف",
    "Committed {count} changing statements, {rows} rows": "تم تثبيت {count} عبارات مبدّلة للبيانات، {rows} صف",
    "Rolled back {count} changing statement": "تم التراجع عن {count} عبارة مبدّلة للبيانات",
    "Rolled back {count} changing statements": "تم التراجع عن {count} عبارات مبدّلة للبيانات",
    "Document deleted": "حُذف المستند",
    "{count} runs deleted": "عمليات تشغيل محذوفة: {count}",
    # البحث.
    "Favorites": "المفضلة",
    "Untitled query": "استعلام بلا عنوان",
    "Only the newest {count} saved queries are searched by their title": "لا يُبحث بالعنوان إلا في أحدث {count} استعلامًا محفوظًا",
    "Stopped before every saved query was read": "توقف قبل قراءة كل استعلام محفوظ",
    "Only the newest {count} saved queries are searched by their text": "لا يُبحث بالنص إلا في أحدث {count} استعلامًا محفوظًا",
    "Saved query": "استعلام محفوظ",
    "Saved query · {connection}": "استعلام محفوظ · {connection}",
}
