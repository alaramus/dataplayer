"""What FTP writes, in Hindi (D226).

The file side is the explorer's and words itself; these are the words of the
server, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "FTP": "FTP",
    "A server reached over FTP or FTPS. Browse its folders from where you choose and work with its files as with your own: tables, SQL over files, the editor, archives, search and copying between connections. Signs in with a password or anonymously.": "FTP या FTPS से पहुँचा जाने वाला सर्वर। अपनी चुनी जगह से उसके फ़ोल्डर देखें और उसकी फ़ाइलों के साथ अपनी फ़ाइलों की तरह काम करें: तालिकाएँ, फ़ाइलों पर SQL, एडिटर, आर्काइव, खोज और कनेक्शनों के बीच कॉपी। पासवर्ड से या गुमनाम रूप से साइन इन।",
    "21, or 990 for implicit TLS": "21, या implicit TLS के लिए 990",
    "Encryption": "एन्क्रिप्शन",
    "TLS, explicit": "TLS, explicit",
    "TLS, implicit": "कोई एन्क्रिप्शन नहीं",
    "No encryption": "TLS, implicit",
    "Off only for a server with a certificate of its own making": "केवल स्वयं बनाए प्रमाणपत्र वाले सर्वर के लिए बंद करें",
    "Where browsing starts; empty is the folder the server signs you into": "ब्राउज़िंग कहाँ से शुरू हो; खाली हो तो वह फ़ोल्डर जिसमें सर्वर साइन इन पर ले जाता है",
    "The host is a name or an address, without a scheme or a path": "होस्ट एक नाम या पता है, बिना स्कीम या पथ के",
    "The folder is one line": "फ़ोल्डर एक पंक्ति में लिखा जाता है",
    "The user is one line": "उपयोगकर्ता एक पंक्ति में लिखा जाता है",
    "A name with a line break in it cannot be sent to the server": "पंक्ति विराम वाला नाम सर्वर को नहीं भेजा जा सकता",
    "Every connection to the server is busy": "सर्वर के सभी कनेक्शन व्यस्त हैं",
    "That is not an FTP address": "यह FTP पता नहीं है",
    "The FTP connection has no host": "FTP कनेक्शन में होस्ट नहीं है",
    "The TLS connection to the server failed": "सर्वर से TLS कनेक्शन विफल रहा",
    "The file is no longer on the server": "फ़ाइल अब सर्वर पर नहीं है",
    "The server closed the connection": "सर्वर ने कनेक्शन बंद कर दिया",
    "The server did not accept this user and password": "सर्वर ने यह उपयोगकर्ता और पासवर्ड स्वीकार नहीं किया",
    "The server does not let anonymous users in": "सर्वर गुमनाम उपयोगकर्ताओं को अंदर नहीं आने देता",
    "The server does not offer TLS; choose no encryption to sign in without it": "सर्वर TLS नहीं देता; इसके बिना साइन इन करने के लिए कोई एन्क्रिप्शन नहीं चुनें",
    "The server has too many connections open": "सर्वर के बहुत अधिक कनेक्शन खुले हैं",
    "The server is busy; try again": "सर्वर व्यस्त है; फिर से कोशिश करें",
    "The server refused that": "सर्वर ने इसे अस्वीकार कर दिया",
    "The server's certificate was not accepted": "सर्वर का प्रमाणपत्र स्वीकार नहीं किया गया",
    "The server's name could not be resolved": "सर्वर का नाम हल नहीं हो सका",
    "There is no such folder on the server": "सर्वर पर ऐसा कोई फ़ोल्डर नहीं है",
}
