"""What S3 writes, in Hindi (D226).

The file side is the explorer's and words itself; these are the words of the
store, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "S3": "S3",
    "Amazon S3 or a store that speaks its API. Browse buckets and folders and work with objects as with your own files: tables, SQL over files, the editor, archives, search and copying between connections. Buckets are made and deleted here too. Signs in with an access key.": "Amazon S3 या उसका API समझने वाला स्टोर। बकेट और फ़ोल्डर देखें और ऑब्जेक्ट के साथ अपनी फ़ाइलों की तरह काम करें: तालिकाएँ, फ़ाइलों पर SQL, एडिटर, संग्रह, खोज और कनेक्शनों के बीच कॉपी। बकेट भी यहीं बनाए और हटाए जाते हैं। एक्सेस कुंजी से साइन इन होता है।",
    "The store's address, such as https://s3.example.com; empty for Amazon S3": "स्टोर का पता, जैसे https://s3.example.com; Amazon S3 के लिए खाली",
    "Region": "क्षेत्र",
    "Empty is us-east-1": "खाली का अर्थ us-east-1",
    "Access key": "एक्सेस कुंजी",
    "Bucket": "बकेट",
    "Empty shows every bucket this key may list": "खाली रखने पर वे सभी बकेट दिखते हैं जिन्हें यह कुंजी सूचीबद्ध कर सकती है",
    "Where browsing starts inside the bucket": "बकेट के भीतर ब्राउज़ करना कहाँ से शुरू होता है",
    "Addressing": "एड्रेसिंग",
    "Auto is virtual-hosted on Amazon S3 and path-style elsewhere": "ऑटो: Amazon S3 पर virtual-hosted और बाकी जगह path-style",
    "Verify the certificate": "प्रमाणपत्र जाँचें",
    "Off only for a store with a certificate of its own making": "केवल स्वयं बनाए प्रमाणपत्र वाले स्टोर के लिए बंद करें",
    "The endpoint must be an http or https address": "एंडपॉइंट http या https पता होना चाहिए",
    "A bucket is one name, without slashes": "बकेट एक नाम है, बिना स्लैश के",
    "The folder must stay inside the bucket": "फ़ोल्डर बकेट के भीतर ही रहना चाहिए",
    "A folder needs the bucket it is in": "फ़ोल्डर के लिए वह बकेट चाहिए जिसमें वह है",
    "The store does not know this access key": "स्टोर इस एक्सेस कुंजी को नहीं पहचानता",
    "The secret key does not match the access key": "गुप्त कुंजी एक्सेस कुंजी से मेल नहीं खाती",
    "The store does not let this key do that": "स्टोर इस कुंजी को यह करने नहीं देता",
    "There is no such bucket in this store": "इस स्टोर में ऐसा कोई बकेट नहीं है",
    "The bucket is in another region than this connection names": "बकेट उस क्षेत्र से अलग क्षेत्र में है जो यह कनेक्शन बताता है",
    "This object is archived and has to be restored first": "यह ऑब्जेक्ट संग्रहीत है और पहले इसे पुनर्स्थापित करना होगा",
    "That is no longer in the store": "यह अब स्टोर में नहीं है",
    "The store's certificate was not accepted": "स्टोर का प्रमाणपत्र स्वीकार नहीं किया गया",
    "The store did not answer in time": "स्टोर ने समय पर उत्तर नहीं दिया",
    "Could not reach the store": "स्टोर तक नहीं पहुँचा जा सका",
    "The store could not do that": "स्टोर यह नहीं कर सका",
    "Only buckets are kept at the root of the store": "स्टोर के रूट में केवल बकेट रखे जाते हैं",
    "{name} holds more than {count} objects; this store changes them one by one, so it is refused": "{name} में {count} से अधिक ऑब्जेक्ट हैं; यह स्टोर उन्हें एक-एक करके बदलता है, इसलिए इसे अस्वीकार किया गया",
    "The store did not delete every object": "स्टोर ने हर ऑब्जेक्ट नहीं हटाया",
    "A bucket is not renamed or copied as a whole": "बकेट को पूरा का पूरा नाम बदला या कॉपी नहीं किया जाता",
    "A bucket's name is 3 to 63 lowercase letters, digits, dots and hyphens, beginning and ending with a letter or a digit": "बकेट का नाम 3 से 63 छोटे अक्षरों, अंकों, बिंदुओं और हाइफ़न का होता है, और अक्षर या अंक से शुरू और खत्म होता है",
    "{name} keeps old versions of its objects; empty it with a lifecycle rule, then delete it": "{name} अपने ऑब्जेक्ट के पुराने संस्करण रखता है; पहले उसे लाइफ़साइकल नियम से खाली करें, फिर हटाएँ",
}
