"""ClickHouse जो लिखता है, हिन्दी में (D226)। शब्द स्क्रीन की शब्दावली का पालन करते हैं।"""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ClickHouse": "ClickHouse",
    'A ClickHouse server, over its HTTP interface. Browse databases, tables and views, read and edit rows a page at a time with sorting and filtering done by the server, and run SQL.': 'अपने HTTP इंटरफ़ेस के ज़रिए एक ClickHouse सर्वर। डेटाबेस, तालिकाएँ और व्यू देखें, पंक्तियाँ पृष्ठ-दर-पृष्ठ पढ़ें और संपादित करें जिनकी छँटाई और फ़िल्टरिंग सर्वर करता है, और SQL चलाएँ।',
    "The HTTP interface: 8123, or 8443 with TLS": "HTTP इंटरफ़ेस: 8123, या TLS के साथ 8443",
    "TLS": "TLS",
    "HTTPS, with the server's certificate verified": "HTTPS, सर्वर के प्रमाणपत्र की जाँच के साथ",
    "That is not a ClickHouse connection string": "यह ClickHouse कनेक्शन स्ट्रिंग नहीं है",
    "ClickHouse {version} is older than this source supports ({oldest})": "ClickHouse {version} उससे पुराना है जितना यह स्रोत समर्थन करता है ({oldest})",
    # Relations and rows.
    'This ClickHouse source does not offer the "{representation}" content representation': "यह ClickHouse स्रोत “{representation}” सामग्री प्रस्तुति नहीं देता",
    "A filter value does not fit its column": "फ़िल्टर का मान अपने कॉलम में फ़िट नहीं होता",
    "Changing the structure of a ClickHouse table is not supported yet": "ClickHouse तालिका की संरचना बदलना अभी समर्थित नहीं है",
    # The console.
    'ClickHouse keeps a change the moment it is made and cannot undo it, so a change cannot share a run with other statements; run it on its own': 'ClickHouse कोई बदलाव होते ही उसे रख लेता है और उसे पूर्ववत नहीं कर सकता, इसलिए बदलाव अन्य कथनों के साथ एक ही रन में नहीं चल सकता; इसे अलग से चलाएँ',
    'Detaching and attaching tables is not done from the query editor': 'तालिकाओं को क्वेरी संपादक से अलग या संलग्न नहीं किया जाता',
    'Named collections are not changed from the query editor': 'नामित संग्रह क्वेरी संपादक से नहीं बदले जाते',
    'SYSTEM commands manage the server and are not run from the query editor': 'SYSTEM कमांड सर्वर का प्रबंधन करती हैं और क्वेरी संपादक से नहीं चलाई जातीं',
    'The console shows a result itself; leave FORMAT out': 'कंसोल परिणाम स्वयं दिखाता है; FORMAT हटा दें',
    'The query editor changes databases, tables, views and dictionaries; this is something else': 'क्वेरी संपादक डेटाबेस, तालिकाएँ, व्यू और शब्दकोश बदलता है; यह कुछ और है',
    # Changing rows.
    "A column of the table's key cannot be changed": 'तालिका की कुंजी का कॉलम बदला नहीं जा सकता',
    'A {engine} table does not keep rows inserted into it': '{engine} तालिका उसमें डाली गई पंक्तियाँ नहीं रखती',
    'Another row differs from this one only in a column that cannot be compared exactly, so this one cannot be told apart': 'एक दूसरी पंक्ति इससे केवल ऐसे कॉलम में भिन्न है जिसकी सटीक तुलना नहीं हो सकती, इसलिए इस पंक्ति को उससे अलग नहीं पहचाना जा सकता',
    "Only a MergeTree table's rows can be changed; this one is {engine}": 'केवल MergeTree तालिका की पंक्तियाँ बदली जा सकती हैं; यह {engine} है',
}
