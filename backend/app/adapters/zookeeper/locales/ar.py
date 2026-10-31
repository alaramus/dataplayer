"""ما يكتبه ZooKeeper، بالعربية (D226)."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ZooKeeper": "ZooKeeper",
    "A ZooKeeper server. Walk its znode tree, read a znode's data as text or as JSON with its stat and ACL, edit the data against the version read, and page through a znode's children as rows.": "خادم ZooKeeper. تجوّل في شجرة znode، واقرأ بيانات znode نصًا أو JSON مع stat وACL الخاصين به، وعدّل البيانات مقابل الإصدار المقروء، وتصفّح أبناء znode صفحةً صفحة كصفوف.",
    "Anonymous": "مجهول",
    "Digest": "Digest",
    "Root path": "المسار الجذر",
    "Everything is read under this path, as if it were the top; empty for the whole tree": "يُقرأ كل شيء تحت هذا المسار كأنه القمة؛ اتركه فارغًا للشجرة كلها",
    "A root path starts with / and does not end with one": "يبدأ المسار الجذر بـ / ولا ينتهي بها",
    "A root path has no empty, . or .. parts": "لا يحتوي المسار الجذر على أجزاء فارغة ولا . ولا ..",
    "A ZooKeeper connect string carries no user; choose Digest instead": "سلسلة اتصال ZooKeeper لا تحمل مستخدمًا؛ اختر Digest بدلًا من ذلك",
    "Could not reach the ZooKeeper server": "تعذّر الوصول إلى خادم ZooKeeper",
    "The root path does not exist on this server": "المسار الجذر غير موجود على هذا الخادم",
    "The ZooKeeper server could not do that": "لم يتمكن خادم ZooKeeper من فعل ذلك",
    "The ZooKeeper server refused that": "رفض خادم ZooKeeper ذلك",
    "This connection may not do that to this znode": "لا يحق لهذا الاتصال فعل ذلك بهذا znode",
    "A znode with that name already exists": "يوجد znode بهذا الاسم بالفعل",
    "The znode has children": "لهذا znode أبناء",
    "The server refused that ACL": "رفض الخادم قائمة ACL هذه",
    # Znodes and their data.
    '"{node_id}" is not a znode of this source': "«{node_id}» ليس znode في هذا المصدر",
    "A znode is opened as text or as a JSON tree": "يُفتح znode نصًا أو شجرة JSON",
    "View the data as JSON": "عرض البيانات بصيغة JSON",
    "Edit the data": "تعديل البيانات",
    "View the children": "عرض الأبناء",
    "The data is not JSON": "البيانات ليست JSON",
    "The data is not UTF-8 text, so it is shown as hex": "البيانات ليست نص UTF-8، لذا تُعرض بالنظام الست عشري",
    "The data is not UTF-8 text, so it is shown as hex and not edited here": "البيانات ليست نص UTF-8، لذا تُعرض بالنظام الست عشري ولا تُعدَّل هنا",
}
