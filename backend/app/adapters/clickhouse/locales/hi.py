"""ClickHouse जो लिखता है, हिन्दी में (D226)। शब्द स्क्रीन की शब्दावली का पालन करते हैं।"""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ClickHouse": "ClickHouse",
    "A ClickHouse server, over its HTTP interface. Browse databases, tables and views, and read rows a page at a time with sorting and filtering done by the server.": "अपने HTTP इंटरफ़ेस के ज़रिए एक ClickHouse सर्वर। डेटाबेस, तालिकाएँ और व्यू देखें, और पंक्तियाँ पृष्ठ-दर-पृष्ठ पढ़ें, जिनकी छँटाई और फ़िल्टरिंग सर्वर करता है।",
    "The HTTP interface: 8123, or 8443 with TLS": "HTTP इंटरफ़ेस: 8123, या TLS के साथ 8443",
    "TLS": "TLS",
    "HTTPS, with the server's certificate verified": "HTTPS, सर्वर के प्रमाणपत्र की जाँच के साथ",
    "That is not a ClickHouse connection string": "यह ClickHouse कनेक्शन स्ट्रिंग नहीं है",
    "ClickHouse {version} is older than this source supports ({oldest})": "ClickHouse {version} उससे पुराना है जितना यह स्रोत समर्थन करता है ({oldest})",
    # Relations and rows.
    'This ClickHouse source does not offer the "{representation}" content representation': "यह ClickHouse स्रोत “{representation}” सामग्री प्रस्तुति नहीं देता",
    "A filter value does not fit its column": "फ़िल्टर का मान अपने कॉलम में फ़िट नहीं होता",
    "Changing the structure of a ClickHouse table is not supported yet": "ClickHouse तालिका की संरचना बदलना अभी समर्थित नहीं है",
    "Editing ClickHouse rows is not supported yet": "ClickHouse पंक्तियों को संपादित करना अभी समर्थित नहीं है",
}
