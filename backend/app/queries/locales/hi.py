"""What running a query writes, in Hindi (D226). Terms follow the interface glossary."""

MESSAGES: dict[str, str] = {
    # Before running.
    "There is nothing to run": "चलाने के लिए कुछ नहीं है",
    "This is more than one statement; run it as a script to run them all": "यह एक से अधिक कथन हैं; सभी को चलाने के लिए इसे स्क्रिप्ट के रूप में चलाएँ",
    "A script may hold at most {count} statements": "एक स्क्रिप्ट में अधिकतम {count} कथन हो सकते हैं",
    "Statement {at} is larger than one statement may be": "कथन {at} एक कथन की अनुमत सीमा से बड़ा है",
    "Statement {at}: {refusal}": "कथन {at}: {refusal}",
    "Maintenance commands run outside a transaction; turn the manual transaction off to run this": "रखरखाव कमांड ट्रांज़ैक्शन के बाहर चलते हैं; इसे चलाने के लिए मैन्युअल ट्रांज़ैक्शन बंद करें",
    "A maintenance command runs outside a transaction, so run it on its own": "रखरखाव कमांड ट्रांज़ैक्शन के बाहर चलता है, इसलिए इसे अकेले चलाएँ",
    "Statement {at} is a {kind} statement, and this run is a read": "कथन {at} एक {kind} कथन है, और यह रन एक पढ़ाई है",
    "Statement {at} is a {kind} statement, and statements of that kind are not run here": "कथन {at} एक {kind} कथन है, और उस प्रकार के कथन यहाँ नहीं चलाए जाते",
    "No value was given for {names}": "{names} के लिए कोई मान नहीं दिया गया",
    # Writes.
    "A write cannot run in read mode": "पढ़ने के मोड में लेखन नहीं चल सकता",
    "The owner of this connection allows reading only": "इस कनेक्शन का स्वामी केवल पढ़ने की अनुमति देता है",
    "A {kind} statement needs read access to this connection": "{kind} कथन के लिए इस कनेक्शन तक पढ़ने की पहुँच आवश्यक है",
    "A {kind} statement needs write access to this connection": "{kind} कथन के लिए इस कनेक्शन तक लिखने की पहुँच आवश्यक है",
    "A {kind} statement needs structure access to this connection": "{kind} कथन के लिए इस कनेक्शन तक संरचना की पहुँच आवश्यक है",
    "A {kind} statement needs own access to this connection": "{kind} कथन के लिए इस कनेक्शन तक स्वामी पहुँच आवश्यक है",
    "Confirm this write before running it": "इसे चलाने से पहले इस लेखन की पुष्टि करें",
    "This run asks for something that cannot be undone; confirm it first": "यह रन ऐसा कुछ माँगता है जिसे वापस नहीं किया जा सकता; पहले इसकी पुष्टि करें",
    "You have read access to this connection": "आपके पास इस कनेक्शन तक पढ़ने की पहुँच है",
    # A run.
    "This run could not be completed": "यह रन पूरा नहीं हो सका",
    "There was no room to keep this result": "इस परिणाम को रखने के लिए जगह नहीं थी",
    # Transactions and history.
    "Committed {count} changing statement, {rows} rows": "{count} परिवर्तनकारी कथन कमिट किया, {rows} पंक्तियाँ",
    "Committed {count} changing statements, {rows} rows": "{count} परिवर्तनकारी कथन कमिट किए, {rows} पंक्तियाँ",
    "Rolled back {count} changing statement": "{count} परिवर्तनकारी कथन रोल बैक किया",
    "Rolled back {count} changing statements": "{count} परिवर्तनकारी कथन रोल बैक किए",
    "Document deleted": "दस्तावेज़ हटाया गया",
    "{count} runs deleted": "{count} रन हटाए गए",
    # Search.
    "Favorites": "पसंदीदा",
    "Untitled query": "बिना शीर्षक वाली क्वेरी",
    "Only the newest {count} saved queries are searched by their title": "केवल नवीनतम {count} सहेजी गई क्वेरियाँ उनके शीर्षक से खोजी जाती हैं",
    "Stopped before every saved query was read": "हर सहेजी गई क्वेरी पढ़े जाने से पहले रोका गया",
    "Only the newest {count} saved queries are searched by their text": "केवल नवीनतम {count} सहेजी गई क्वेरियाँ उनके टेक्स्ट से खोजी जाती हैं",
    "Saved query": "सहेजी गई क्वेरी",
    "Saved query · {connection}": "सहेजी गई क्वेरी · {connection}",
}
