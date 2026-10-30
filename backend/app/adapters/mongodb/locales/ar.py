"""ما يكتبه MongoDB بالعربية (D226)."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "MongoDB": "MongoDB",
    "A MongoDB server. Browse databases, collections and views, and read documents a page at a time as rows, their fields found from the documents themselves, with sorting and filtering done by the server.": "خادم MongoDB. تصفّح قواعد البيانات والمجموعات وطرق العرض، واقرأ المستندات صفحةً صفحةً كصفوف، تُستخرج حقولها من المستندات نفسها، ويتولى الخادم الفرز والتصفية.",
    "Authentication database": "قاعدة بيانات المصادقة",
    "Where the user is defined; admin unless it was made in another database": "حيث عُرِّف المستخدم؛ admin ما لم يُنشأ في قاعدة بيانات أخرى",
    "Encrypted, with the server's certificate verified": "مشفّر، مع التحقق من شهادة الخادم",
    "That is not a MongoDB connection string": "هذه ليست سلسلة اتصال MongoDB",
    "A mongodb+srv address is not supported; name one server with mongodb://": "عنوان mongodb+srv غير مدعوم؛ حدّد خادمًا واحدًا باستخدام mongodb://",
    "Name one server; a list of servers is not supported": "حدّد خادمًا واحدًا؛ قائمة الخوادم غير مدعومة",
    "MongoDB {version} is older than this source supports ({oldest})": "الإصدار MongoDB {version} أقدم مما يدعمه هذا المصدر ({oldest})",
    "The server asks for a user and a password": "يطلب الخادم مستخدمًا وكلمة مرور",
    "The connection settings are not usable": "لا يمكن الاتصال بهذه الإعدادات",
    "The server refused the request": "رفض الخادم الطلب",
    # Collections and documents.
    "View the definition": "عرض التعريف",
    '"{node_id}" is not a collection: expected database.collection': "«{node_id}» ليست مجموعة: المتوقع قاعدة_البيانات.المجموعة",
    '"{name}" belongs to the server': "«{name}» تخص الخادم",
    "A collection has no columns of its own; every document has its own fields": "ليس للمجموعة أعمدة خاصة بها؛ لكل مستند حقوله الخاصة",
    "Indexes are not changed here yet": "لا تُعدَّل الفهارس هنا بعد",
    "MongoDB has no constraints but unique indexes": "لا توجد في MongoDB قيود سوى الفهارس الفريدة",
    "Documents are not changed here yet": "لا تُعدَّل المستندات هنا بعد",
    'This MongoDB source does not offer the "{representation}" content representation': "لا يقدّم مصدر MongoDB هذا تمثيل المحتوى «{representation}»",
}
