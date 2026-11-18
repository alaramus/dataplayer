"""What S3 writes, in Hindi (D226).

The file side is the explorer's and words itself; these are the words of the
store, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "S3": "S3",
    "Amazon S3 or a store that speaks its API. Browse buckets and folders and work with objects as with your own files: tables, SQL over files, the viewers and search. Signs in with an access key.": "Amazon S3 या उसका API समझने वाला स्टोर। बकेट और फ़ोल्डर देखें और ऑब्जेक्ट के साथ अपनी फ़ाइलों की तरह काम करें: तालिकाएँ, फ़ाइलों पर SQL, व्यूअर और खोज। एक्सेस कुंजी से साइन इन होता है।",
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
}
