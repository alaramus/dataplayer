"""MongoDB जो लिखता है, हिन्दी में (D226)। शब्द स्क्रीन की शब्दावली का पालन करते हैं।"""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "MongoDB": "MongoDB",
    "A MongoDB server. Browse databases, collections and views, and read documents a page at a time as rows, their fields found from the documents themselves, with sorting and filtering done by the server.": "एक MongoDB सर्वर। डेटाबेस, कलेक्शन और व्यू ब्राउज़ करें, और दस्तावेज़ों को पंक्तियों के रूप में एक-एक पेज पढ़ें; उनके फ़ील्ड दस्तावेज़ों से ही पहचाने जाते हैं, और सॉर्टिंग व फ़िल्टरिंग सर्वर करता है।",
    "Authentication database": "प्रमाणीकरण डेटाबेस",
    "Where the user is defined; admin unless it was made in another database": "जहाँ उपयोगकर्ता परिभाषित है; admin, जब तक वह किसी दूसरे डेटाबेस में न बनाया गया हो",
    "Encrypted, with the server's certificate verified": "एन्क्रिप्टेड, सर्वर के प्रमाणपत्र की जाँच के साथ",
    "That is not a MongoDB connection string": "यह MongoDB कनेक्शन स्ट्रिंग नहीं है",
    "A mongodb+srv address is not supported; name one server with mongodb://": "mongodb+srv पता समर्थित नहीं है; mongodb:// से एक सर्वर बताएँ",
    "Name one server; a list of servers is not supported": "एक सर्वर बताएँ; सर्वरों की सूची समर्थित नहीं है",
    "MongoDB {version} is older than this source supports ({oldest})": "MongoDB {version} इस स्रोत द्वारा समर्थित संस्करण ({oldest}) से पुराना है",
    "The server asks for a user and a password": "सर्वर उपयोगकर्ता और पासवर्ड माँगता है",
    "The connection settings are not usable": "इन कनेक्शन सेटिंग्स से कनेक्ट नहीं किया जा सकता",
    "The server refused the request": "सर्वर ने अनुरोध अस्वीकार कर दिया",
    # Collections and documents.
    "View the definition": "परिभाषा देखें",
    '"{node_id}" is not a collection: expected database.collection': "\"{node_id}\" कलेक्शन नहीं है: database.collection अपेक्षित है",
    '"{name}" belongs to the server': "\"{name}\" सर्वर का है",
    "A collection has no columns of its own; every document has its own fields": "कलेक्शन के अपने कॉलम नहीं होते; हर दस्तावेज़ के अपने फ़ील्ड होते हैं",
    "Indexes are not changed here yet": "इंडेक्स यहाँ अभी नहीं बदले जाते",
    "MongoDB has no constraints but unique indexes": "MongoDB में यूनिक इंडेक्स के अलावा कोई कंस्ट्रेंट नहीं होते",
    "Documents are not changed here yet": "दस्तावेज़ यहाँ अभी नहीं बदले जाते",
    'This MongoDB source does not offer the "{representation}" content representation': "यह MongoDB स्रोत \"{representation}\" सामग्री प्रस्तुति नहीं देता",
}
