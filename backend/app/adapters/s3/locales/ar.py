"""What S3 writes, in Arabic (D226).

The file side is the explorer's and words itself; these are the words of the
store, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "S3": "S3",
    "Amazon S3 or a store that speaks its API. Browse buckets and folders and work with objects as with your own files: tables, SQL over files, the editor, archives, search and copying between connections. Buckets are made and deleted here too. Signs in with an access key.": "Amazon S3 أو مخزن يتحدث واجهته البرمجية. تصفّح الحاويات والمجلدات واعمل مع الكائنات كما مع ملفاتك: الجداول وSQL على الملفات والمحرر والأرشيفات والبحث والنسخ بين الاتصالات. وتُنشأ الحاويات وتُحذف هنا أيضًا. يُسجَّل الدخول بمفتاح وصول.",
    "The store's address, such as https://s3.example.com; empty for Amazon S3": "عنوان المخزن، مثل https://s3.example.com؛ فارغ لـ Amazon S3",
    "Region": "المنطقة",
    "Empty is us-east-1": "الفارغ يعني us-east-1",
    "Access key": "مفتاح الوصول",
    "Bucket": "الحاوية",
    "Empty shows every bucket this key may list": "الفارغ يعرض كل حاوية يمكن لهذا المفتاح سردها",
    "Where browsing starts inside the bucket": "من أين يبدأ التصفح داخل الحاوية",
    "Addressing": "العنونة",
    "Auto is virtual-hosted on Amazon S3 and path-style elsewhere": "التلقائي هو virtual-hosted على Amazon S3 وpath-style في غيره",
    "Verify the certificate": "التحقق من الشهادة",
    "Off only for a store with a certificate of its own making": "أوقفه فقط لمخزن بشهادة من صنعه",
    "The endpoint must be an http or https address": "يجب أن تكون نقطة الوصول عنوان http أو https",
    "A bucket is one name, without slashes": "الحاوية اسم واحد، بلا شرطات مائلة",
    "The folder must stay inside the bucket": "يجب أن يبقى المجلد داخل الحاوية",
    "A folder needs the bucket it is in": "يحتاج المجلد إلى الحاوية التي هو فيها",
    "The store does not know this access key": "لا يعرف المخزن مفتاح الوصول هذا",
    "The secret key does not match the access key": "المفتاح السري لا يطابق مفتاح الوصول",
    "The store does not let this key do that": "لا يسمح المخزن لهذا المفتاح بذلك",
    "There is no such bucket in this store": "لا توجد حاوية بهذا الاسم في هذا المخزن",
    "The bucket is in another region than this connection names": "الحاوية في منطقة غير التي يذكرها هذا الاتصال",
    "This object is archived and has to be restored first": "هذا الكائن مؤرشف ويجب استعادته أولًا",
    "That is no longer in the store": "لم يعد هذا في المخزن",
    "The store's certificate was not accepted": "لم تُقبل شهادة المخزن",
    "The store did not answer in time": "لم يُجب المخزن في الوقت المحدد",
    "Could not reach the store": "تعذّر الوصول إلى المخزن",
    "The store could not do that": "لم يتمكن المخزن من فعل ذلك",
    "Only buckets are kept at the root of the store": "لا يحفظ جذر المخزن إلا الحاويات",
    "{name} holds more than {count} objects; this store changes them one by one, so it is refused": "يحوي {name} أكثر من {count} كائن؛ يغيّرها هذا المخزن واحدًا واحدًا، لذا رُفض ذلك",
    "The store did not delete every object": "لم يحذف المخزن كل الكائنات",
    "A bucket is not renamed or copied as a whole": "لا تُعاد تسمية الحاوية ولا تُنسخ كاملة",
    "A bucket's name is 3 to 63 lowercase letters, digits, dots and hyphens, beginning and ending with a letter or a digit": "اسم الحاوية من 3 إلى 63 حرفًا لاتينيًا صغيرًا ورقمًا ونقطة وشرطة، يبدأ وينتهي بحرف أو رقم",
    "{name} keeps old versions of its objects; empty it with a lifecycle rule, then delete it": "يحتفظ {name} بإصدارات قديمة من كائناته؛ أفرغه بقاعدة دورة حياة ثم احذفه",
}
