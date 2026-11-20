"""What FTP writes, in Arabic (D226).

The file side is the explorer's and words itself; these are the words of the
server, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "FTP": "FTP",
    "A server reached over FTP or FTPS. Browse its folders from where you choose and work with its files as with your own: tables, SQL over files, the editor, archives, search and copying between connections. Signs in with a password or anonymously.": "خادم يُوصل إليه عبر FTP أو FTPS. تصفّح مجلداته بدءًا من المكان الذي تختاره واعمل على ملفاته كما تعمل على ملفاتك: الجداول وSQL على الملفات والمحرر والأرشيفات والبحث والنسخ بين الاتصالات. يسجّل الدخول بكلمة مرور أو دون اسم.",
    "21, or 990 for implicit TLS": "21، أو 990 لـ TLS الضمني",
    "Encryption": "التشفير",
    "TLS, explicit": "TLS، صريح",
    "TLS, implicit": "TLS، ضمني",
    "No encryption": "دون تشفير",
    "Off only for a server with a certificate of its own making": "أوقفه فقط لخادم بشهادة من صنعه",
    "Where browsing starts; empty is the folder the server signs you into": "من أين يبدأ التصفح؛ الفارغ هو المجلد الذي يدخلك إليه الخادم عند تسجيل الدخول",
    "The host is a name or an address, without a scheme or a path": "المضيف اسم أو عنوان، دون مخطط أو مسار",
    "The folder is one line": "المجلد سطر واحد",
    "The user is one line": "المستخدم سطر واحد",
    "A name with a line break in it cannot be sent to the server": "لا يمكن إرسال اسم فيه فاصل أسطر إلى الخادم",
    "Every connection to the server is busy": "كل الاتصالات بالخادم مشغولة",
    "That is not an FTP address": "هذا ليس عنوان FTP",
    "The FTP connection has no host": "اتصال FTP بلا مضيف",
    "The TLS connection to the server failed": "فشل اتصال TLS بالخادم",
    "The file is no longer on the server": "لم يعد الملف على الخادم",
    "The server closed the connection": "أغلق الخادم الاتصال",
    "The server did not accept this user and password": "لم يقبل الخادم هذا المستخدم وكلمة المرور",
    "The server does not let anonymous users in": "لا يسمح الخادم بالمستخدمين المجهولين",
    "The server does not offer TLS; choose no encryption to sign in without it": "لا يقدّم الخادم TLS؛ اختر دون تشفير لتسجيل الدخول بدونه",
    "The server has too many connections open": "لدى الخادم اتصالات مفتوحة كثيرة جدًا",
    "The server is busy; try again": "الخادم مشغول؛ حاول مرة أخرى",
    "The server refused that": "رفض الخادم ذلك",
    "The server's certificate was not accepted": "لم تُقبل شهادة الخادم",
    "The server's name could not be resolved": "تعذّر تحليل اسم الخادم",
    "There is no such folder on the server": "لا يوجد مجلد كهذا على الخادم",
}
