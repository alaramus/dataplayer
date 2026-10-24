"""What SQLite writes, in Hindi (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "SQLite": "SQLite",
    'A SQLite database file in your personal storage. Browse its tables and views, read rows a page at a time with sorting and filtering, and run SQL.': 'आपके व्यक्तिगत संग्रहण में एक SQLite डेटाबेस फ़ाइल। इसकी टेबल और व्यू देखें, सॉर्टिंग व फ़िल्टरिंग के साथ पंक्तियाँ एक-एक पेज पढ़ें, और SQL चलाएँ।',
    "Database file": "डेटाबेस फ़ाइल",
    "Path of the file inside your personal storage, such as data/shop.db": "आपके व्यक्तिगत संग्रहण में फ़ाइल का पथ, जैसे data/shop.db",
    "Create the file if it is missing": "फ़ाइल न हो तो बनाएँ",
    "Without this, a file that does not exist fails the connection check": "इसके बिना, जो फ़ाइल मौजूद नहीं है वह कनेक्शन जाँच में विफल होती है",
    "Name a file inside your personal storage": "अपने व्यक्तिगत संग्रहण में एक फ़ाइल बताएँ",
    # Opening the file.
    "SQLite {version} is older than this source supports ({oldest})": "SQLite {version} उससे पुराना है जितना यह स्रोत समर्थन करता है ({oldest})",
    "The database file does not exist": "डेटाबेस फ़ाइल मौजूद नहीं है",
    "The folder for the database file does not exist": "डेटाबेस फ़ाइल के लिए फ़ोल्डर मौजूद नहीं है",
    "The path names a folder, not a file": "पथ एक फ़ोल्डर बताता है, फ़ाइल नहीं",
    "The file is not a SQLite database": "यह फ़ाइल SQLite डेटाबेस नहीं है",
    "The database file is damaged": "डेटाबेस फ़ाइल क्षतिग्रस्त है",
    "The database file cannot be opened": "डेटाबेस फ़ाइल खोली नहीं जा सकती",
    "The database file cannot be written": "डेटाबेस फ़ाइल में लिखा नहीं जा सकता",
    "The database file is locked by another connection": "डेटाबेस फ़ाइल किसी अन्य कनेक्शन ने लॉक की हुई है",
    "The database did not answer in time": "डेटाबेस ने समय पर उत्तर नहीं दिया",
    # The catalog and its relations.
    '"{name}" needs a module this server does not have': "“{name}” को ऐसा मॉड्यूल चाहिए जो इस सर्वर पर नहीं है",
    '"{node_id}" is not a relation: expected main.table': "“{node_id}” रिलेशन नहीं है: main.टेबल अपेक्षित है",
    'This SQLite source does not offer the "{representation}" content representation': "यह SQLite स्रोत “{representation}” सामग्री प्रस्तुति नहीं देता",
    "Rows of a SQLite file are read only for now": "SQLite फ़ाइल की पंक्तियाँ अभी केवल पढ़ने के लिए हैं",
    # The console.
    'A connection to this file opens no other file': 'इस फ़ाइल का कनेक्शन कोई और फ़ाइल नहीं खोलता',
    'Query plan': 'क्वेरी प्लान',
    'The query editor changes tables, views and indexes; this is something else': 'क्वेरी एडिटर टेबल, व्यू और इंडेक्स बदलता है; यह कुछ और है',
}
