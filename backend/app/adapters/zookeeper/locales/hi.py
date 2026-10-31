"""ZooKeeper जो लिखता है, हिंदी में (D226)।"""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ZooKeeper": "ZooKeeper",
    "A ZooKeeper server. Walk its znode tree, read a znode's data as text or as JSON with its stat and ACL, edit the data against the version read, and page through a znode's children as rows.": "एक ZooKeeper सर्वर। उसके znode ट्री में घूमें, किसी znode का डेटा उसके stat और ACL के साथ टेक्स्ट या JSON के रूप में पढ़ें, पढ़े गए संस्करण के आधार पर डेटा संपादित करें, और किसी znode के चाइल्ड को पंक्तियों के रूप में पृष्ठ-दर-पृष्ठ देखें।",
    "Anonymous": "अनाम",
    "Digest": "Digest",
    "Root path": "रूट पथ",
    "Everything is read under this path, as if it were the top; empty for the whole tree": "सब कुछ इसी पथ के नीचे पढ़ा जाता है, मानो यही शीर्ष हो; पूरे ट्री के लिए खाली छोड़ें",
    "A root path starts with / and does not end with one": "रूट पथ / से शुरू होता है और / पर समाप्त नहीं होता",
    "A root path has no empty, . or .. parts": "रूट पथ में खाली, . या .. भाग नहीं होते",
    "A ZooKeeper connect string carries no user; choose Digest instead": "ZooKeeper कनेक्ट स्ट्रिंग में उपयोगकर्ता नहीं होता; इसके बजाय Digest चुनें",
    "Could not reach the ZooKeeper server": "ZooKeeper सर्वर तक नहीं पहुँचा जा सका",
    "The root path does not exist on this server": "इस सर्वर पर यह रूट पथ मौजूद नहीं है",
    "The ZooKeeper server could not do that": "ZooKeeper सर्वर यह नहीं कर सका",
    "The ZooKeeper server refused that": "ZooKeeper सर्वर ने इसे अस्वीकार कर दिया",
    "This connection may not do that to this znode": "यह कनेक्शन इस znode के साथ ऐसा नहीं कर सकता",
    "A znode with that name already exists": "इस नाम का znode पहले से मौजूद है",
    "The znode has children": "इस znode के चाइल्ड हैं",
    "The server refused that ACL": "सर्वर ने वह ACL अस्वीकार कर दिया",
    # Znodes and their data.
    '"{node_id}" is not a znode of this source': '"{node_id}" इस स्रोत का znode नहीं है',
    "A znode is opened as text or as a JSON tree": "znode टेक्स्ट या JSON ट्री के रूप में खुलता है",
    "View the data as JSON": "डेटा JSON के रूप में देखें",
    "Edit the data": "डेटा संपादित करें",
    "View the children": "चाइल्ड देखें",
    "The data is not JSON": "डेटा JSON नहीं है",
    "The data is not UTF-8 text, so it is shown as hex": "डेटा UTF-8 टेक्स्ट नहीं है, इसलिए हेक्स में दिखाया गया है",
    "The data is not UTF-8 text, so it is shown as hex and not edited here": "डेटा UTF-8 टेक्स्ट नहीं है, इसलिए हेक्स में दिखाया गया है और यहाँ संपादित नहीं होता",
}
