"""TimescaleDB क्रियाएँ और रिपोर्ट जो लिखती हैं, हिन्दी में (D226)।

शब्दावली इंटरफ़ेस की शब्दावली का पालन करती है; TimescaleDB के अपने फ़ंक्शन
और विकल्प नाम अपरिवर्तित रहते हैं।
"""

MESSAGES: dict[str, str] = {
    # अवधियाँ, जैसा कोई पूर्वावलोकन उन्हें दिखाता है।
    "{amount} second": "{amount} सेकंड",
    "{amount} seconds": "{amount} सेकंड",
    "{amount} minute": "{amount} मिनट",
    "{amount} minutes": "{amount} मिनट",
    "{amount} hour": "{amount} घंटा",
    "{amount} hours": "{amount} घंटे",
    "{amount} day": "{amount} दिन",
    "{amount} days": "{amount} दिन",
    "{amount} week": "{amount} सप्ताह",
    "{amount} weeks": "{amount} सप्ताह",
    "{amount} month": "{amount} महीना",
    "{amount} months": "{amount} महीने",
    "{amount} year": "{amount} वर्ष",
    "{amount} years": "{amount} वर्ष",
    "{amount} value": "{amount} मान",
    "{amount} values": "{amount} मान",
    # रिपोर्ट।
    "Hypertables": "हाइपरटेबल",
    "Hypertable owners, dimension/chunk counts and compression configuration": (
        "हाइपरटेबल के स्वामी, आयाम और चंक की संख्या तथा कम्प्रेशन कॉन्फ़िगरेशन"
    ),
    "Continuous aggregates": "कंटीन्यूअस एग्रीगेट",
    "Aggregate owners, source/materialization identities and configuration": (
        "एग्रीगेट के स्वामी, स्रोत और मटीरियलाइज़ेशन की पहचान तथा कॉन्फ़िगरेशन"
    ),
    "Chunks": "चंक",
    "Chunk identities, primary-dimension boundaries and compression status": (
        "चंक की पहचान, प्राथमिक आयाम की सीमाएँ और कम्प्रेशन स्थिति"
    ),
    "Dimensions": "आयाम",
    "Time, integer and space dimensions of each hypertable": (
        "प्रत्येक हाइपरटेबल के समय, पूर्णांक और स्थान आयाम"
    ),
    "Policies and jobs": "नीतियाँ और जॉब",
    "Native TimescaleDB jobs, including policies and their schedules": (
        "TimescaleDB के मूल जॉब, नीतियों और उनके शेड्यूल सहित"
    ),
    "Job statistics": "जॉब सांख्यिकी",
    "Recorded native job runs, outcomes and counters; unrun jobs may be absent": (
        "दर्ज किए गए मूल जॉब रन, परिणाम और काउंटर; कभी न चले जॉब अनुपस्थित हो सकते हैं"
    ),
    "Detached chunks": "अलग किए गए चंक",
    "Tables named like a chunk that no hypertable holds; Attach chunk takes one back": (
        "चंक जैसे नाम वाली टेबलें जो किसी हाइपरटेबल की नहीं हैं; “चंक संलग्न करें” उनमें से एक को वापस लेता है"
    ),
    "This report cannot be inspected by this connection": "यह कनेक्शन इस रिपोर्ट को नहीं देख सकता",
    "The installed TimescaleDB lacks the public API for this view": (
        "स्थापित TimescaleDB में इस व्यू के लिए सार्वजनिक API नहीं है"
    ),
    # TimescaleDB का पता लगाना।
    "TimescaleDB is not installed on this database": "इस डेटाबेस पर TimescaleDB स्थापित नहीं है",
    "This source has no usable TimescaleDB API": "इस स्रोत में कोई उपयोगी TimescaleDB API नहीं है",
    "This connection may not inspect installed extensions": (
        "यह कनेक्शन स्थापित एक्सटेंशन नहीं देख सकता"
    ),
    "Installed extensions could not be inspected": "स्थापित एक्सटेंशन नहीं देखे जा सके",
    "The installed TimescaleDB version could not be read": "स्थापित TimescaleDB संस्करण पढ़ा नहीं जा सका",
    "TimescaleDB extension metadata could not be read": "TimescaleDB एक्सटेंशन मेटाडेटा पढ़ा नहीं जा सका",
    "This TimescaleDB major version is not supported": "इस TimescaleDB प्रमुख संस्करण का समर्थन नहीं है",
    "This connection may not inspect TimescaleDB metadata": "यह कनेक्शन TimescaleDB मेटाडेटा नहीं देख सकता",
    "TimescaleDB metadata could not be inspected": "TimescaleDB मेटाडेटा नहीं देखा जा सका",
    "The installed version lacks the supported inspection API": (
        "स्थापित संस्करण में समर्थित निरीक्षण API नहीं है"
    ),
    "TimescaleDB action vocabulary could not be inspected": "TimescaleDB क्रिया शब्दावली निर्धारित नहीं की जा सकी",
    "The TimescaleDB {routine} API is not usable by this connection": (
        "यह कनेक्शन TimescaleDB {routine} API का उपयोग नहीं कर सकता"
    ),
    "The TimescaleDB {type} type is not usable by this connection": (
        "यह कनेक्शन TimescaleDB {type} प्रकार का उपयोग नहीं कर सकता"
    ),
    "This connection may not lock TimescaleDB public metadata": (
        "यह कनेक्शन TimescaleDB सार्वजनिक मेटाडेटा को लॉक नहीं कर सकता"
    ),
    # किसी रिलेशन के TimescaleDB तथ्य।
    "TimescaleDB metadata no longer identifies this relation uniquely": (
        "TimescaleDB मेटाडेटा अब इस रिलेशन को विशिष्ट रूप से नहीं पहचानता"
    ),
    "TimescaleDB metadata inspection timed out": "TimescaleDB मेटाडेटा देखने का समय समाप्त हो गया",
    "TimescaleDB metadata could not be inspected safely": "TimescaleDB मेटाडेटा सुरक्षित रूप से नहीं देखा जा सका",
    "TimescaleDB size inspection timed out": "TimescaleDB आकार निर्धारित करने का समय समाप्त हो गया",
    "TimescaleDB compression inspection timed out": "TimescaleDB कम्प्रेशन सांख्यिकी पढ़ने का समय समाप्त हो गया",
    "TimescaleDB size could not be inspected safely": "TimescaleDB आकार सुरक्षित रूप से निर्धारित नहीं किया जा सका",
    "TimescaleDB compression statistics could not be inspected safely": (
        "TimescaleDB कम्प्रेशन सांख्यिकी सुरक्षित रूप से नहीं पढ़ी जा सकी"
    ),
    # वह टेबल जिसे कोई संचालन लक्षित करता है।
    "Choose one user hypertable": "एक उपयोगकर्ता हाइपरटेबल चुनें",
    "Choose one user continuous aggregate": "एक उपयोगकर्ता कंटीन्यूअस एग्रीगेट चुनें",
    "Choose an owned hypertable": "अपने स्वामित्व वाला हाइपरटेबल चुनें",
    "Choose an owned hypertable with one time dimension": (
        "एक समय आयाम वाला अपने स्वामित्व का हाइपरटेबल चुनें"
    ),
    "Choose an owned hypertable partitioned by time": (
        "समय के अनुसार विभाजित अपने स्वामित्व वाला हाइपरटेबल चुनें"
    ),
    "Choose an owned continuous aggregate": "अपने स्वामित्व वाला कंटीन्यूअस एग्रीगेट चुनें",
    "Only timestamp and date dimensions are supported here": "यहाँ केवल timestamp और date आयाम समर्थित हैं",
    "Only a hypertable with one range dimension is maintained here": (
        "यहाँ केवल एक रेंज आयाम वाले हाइपरटेबल का रखरखाव किया जाता है"
    ),
    "Only timestamp, date and integer dimensions are supported here": (
        "यहाँ केवल timestamp, date और पूर्णांक आयाम समर्थित हैं"
    ),
    "Only aggregates over timestamp and date dimensions are supported here": (
        "यहाँ केवल timestamp और date आयामों पर आधारित एग्रीगेट समर्थित हैं"
    ),
    # योजना की समीक्षा करना और उसे लागू करना।
    "The operation plan changed; review it again": "संचालन योजना बदल गई; कृपया इसे फिर से देखें",
    "Validation timed out; review the plan again": "सत्यापन का समय समाप्त हो गया; योजना फिर से देखें",
    "The source changed or is busy; review the plan again": "स्रोत बदल गया या व्यस्त है; योजना फिर से देखें",
    "The change could not be confirmed; reload the source before reviewing again": (
        "परिवर्तन की पुष्टि नहीं हो सकी; दोबारा देखने से पहले स्रोत पुनः लोड करें"
    ),
    "The change ran past its {seconds} seconds and was rolled back": (
        "परिवर्तन {seconds} सेकंड की सीमा से अधिक चला और वापस लौटा दिया गया"
    ),
    "This connection may not make this change or lock its metadata": (
        "यह कनेक्शन यह परिवर्तन नहीं कर सकता या इसका मेटाडेटा लॉक नहीं कर सकता"
    ),
    "The source refused the change": "स्रोत ने परिवर्तन अस्वीकार कर दिया",
    "Runs in Activity, one such job per connection at a time; access is checked again before every chunk": (
        "“गतिविधि” में चलता है, प्रति कनेक्शन एक समय में एक ऐसा जॉब; हर चंक से पहले पहुँच की फिर जाँच होती है"
    ),
    "Runs in Activity, one such job per connection at a time; access is checked again before every unit": (
        "“गतिविधि” में चलता है, प्रति कनेक्शन एक समय में एक ऐसा जॉब; हर इकाई से पहले पहुँच की फिर जाँच होती है"
    ),
    # पूर्वावलोकन में साझा पंक्तियाँ।
    "Time dimension: {column}": "समय आयाम: {column}",
    "Unit": "इकाई",
    "{chunk}: {start} to {end}": "{chunk}: {start} से {end} तक",
    "…and {count} more": "…और {count} अन्य",
    "Whole chunks from the earliest chunk to {end}": "सबसे पहले चंक से {end} तक पूरे चंक",
    "Whole chunks from {start} to {end}": "{start} से {end} तक पूरे चंक",
    "Give an instant with its time zone, such as 2026-01-15T00:00:00Z, or a whole number": (
        "समय क्षेत्र के साथ कोई क्षण दें, जैसे 2026-01-15T00:00:00Z, या एक पूर्ण संख्या"
    ),
    "The number is outside the range of a bigint": "संख्या bigint की सीमा से बाहर है",
    "Both ends are instants, or both are numbers": "दोनों सिरे क्षण होने चाहिएँ, या दोनों संख्याएँ",
    "The range must start before it ends": "सीमा का आरंभ उसके अंत से पहले होना चाहिए",
    "The window must start before it ends": "विंडो का आरंभ उसके अंत से पहले होना चाहिए",
    "Chunks ending at or before": "इस समय तक या इससे पहले समाप्त होने वाले चंक",
    "With its time zone; only chunks lying entirely inside the window are chosen": (
        "समय क्षेत्र सहित; केवल पूरी तरह विंडो के भीतर आने वाले चंक चुने जाते हैं"
    ),
    "and starting at or after": "और इस समय पर या इसके बाद आरंभ होने वाले",
    "Leave empty for every earlier chunk": "सभी पहले के चंक के लिए खाली छोड़ें",
    # चंक अंतराल।
    "Change chunk interval": "चंक अंतराल बदलें",
    "Review the interval plan before applying it": "लागू करने से पहले अंतराल योजना देखें",
    "Future chunk interval changed; existing chunks were not repartitioned": (
        "भविष्य के चंक का अंतराल बदल गया; मौजूदा चंक पुनः विभाजित नहीं किए गए"
    ),
    "Change the future chunk interval for {target}": "{target} के लिए भविष्य का चंक अंतराल बदलें",
    "Current interval: {interval}": "वर्तमान अंतराल: {interval}",
    "Requested interval: {interval}": "अनुरोधित अंतराल: {interval}",
    "Only future chunks use the new interval; existing chunks are not repartitioned": (
        "केवल भविष्य के चंक नया अंतराल उपयोग करते हैं; मौजूदा चंक पुनः विभाजित नहीं होते"
    ),
    "Briefly locks TimescaleDB metadata across this database; new chunk creation may wait": (
        "इस डेटाबेस में TimescaleDB मेटाडेटा को थोड़ी देर लॉक करता है; नए चंक बनाने को प्रतीक्षा करनी पड़ सकती है"
    ),
    "TimescaleDB interval metadata could not be inspected safely": (
        "TimescaleDB अंतराल मेटाडेटा सुरक्षित रूप से नहीं देखा जा सका"
    ),
    "TimescaleDB interval planning timed out": "TimescaleDB अंतराल की योजना बनाने का समय समाप्त हो गया",
    "Calendar chunk intervals are not supported by this strategy": (
        "यह रणनीति कैलेंडर-आधारित चंक अंतराल का समर्थन नहीं करती"
    ),
    "Date dimensions require whole days or weeks": "date आयामों के लिए पूरे दिन या सप्ताह आवश्यक हैं",
    "Interval validation timed out; review the plan again": "अंतराल सत्यापन का समय समाप्त हो गया; योजना फिर से देखें",
    "This connection may not change the interval or lock its metadata": (
        "यह कनेक्शन अंतराल नहीं बदल सकता या इसका मेटाडेटा लॉक नहीं कर सकता"
    ),
    "The source refused the interval change": "स्रोत ने अंतराल परिवर्तन अस्वीकार कर दिया",
    "The interval change could not be confirmed; reload the source before reviewing again": (
        "अंतराल परिवर्तन की पुष्टि नहीं हो सकी; दोबारा देखने से पहले स्रोत पुनः लोड करें"
    ),
    # रिटेंशन और कम्प्रेशन नीतियाँ।
    "Set retention policy": "रिटेंशन नीति सेट करें",
    "Remove retention policy": "रिटेंशन नीति हटाएँ",
    "Set compression policy": "कम्प्रेशन नीति सेट करें",
    "Remove compression policy": "कम्प्रेशन नीति हटाएँ",
    "TimescaleDB will keep dropping old chunks by itself, even after this session ends. Set this policy?": (
        "इस सत्र के समाप्त होने के बाद भी TimescaleDB स्वयं पुराने चंक हटाता रहेगा। यह नीति सेट करें?"
    ),
    "Drop chunks older than": "इससे पुराने चंक हटाएँ",
    "Compress chunks older than": "इससे पुराने चंक कम्प्रेस करें",
    "Set the retention policy for {target}": "{target} के लिए रिटेंशन नीति सेट करें",
    "Remove the retention policy from {target}": "{target} से रिटेंशन नीति हटाएँ",
    "Set the compression policy for {target}": "{target} के लिए कम्प्रेशन नीति सेट करें",
    "Remove the compression policy from {target}": "{target} से कम्प्रेशन नीति हटाएँ",
    "No retention policy exists yet": "अभी कोई रिटेंशन नीति नहीं है",
    "No compression policy exists yet": "अभी कोई कम्प्रेशन नीति नहीं है",
    "older than {age}": "{age} से पुराने",
    "created more than {age} ago": "{age} से अधिक समय पहले बनाए गए",
    "Removes job {job}, which drops chunks {chunks}": "जॉब {job} हटाता है, जो चंक {chunks} हटाता है",
    "Replaces job {job}, which drops chunks {chunks}": "जॉब {job} को बदलता है, जो चंक {chunks} हटाता है",
    "Removes job {job}, which compresses chunks {chunks}": "जॉब {job} हटाता है, जो चंक {chunks} कम्प्रेस करता है",
    "Replaces job {job}, which compresses chunks {chunks}": "जॉब {job} को बदलता है, जो चंक {chunks} कम्प्रेस करता है",
    "The current policy runs every {every}; its replacement uses TimescaleDB's default schedule": (
        "वर्तमान नीति हर {every} चलती है; इसका प्रतिस्थापन TimescaleDB का डिफ़ॉल्ट शेड्यूल उपयोग करता है"
    ),
    "New policy: drop chunks older than {age}": "नई नीति: {age} से पुराने चंक हटाएँ",
    "New policy: compress chunks older than {age}": "नई नीति: {age} से पुराने चंक कम्प्रेस करें",
    "TimescaleDB keeps dropping whole chunks older than this on its own schedule, after this session ends": (
        "इस सत्र के समाप्त होने के बाद TimescaleDB अपने शेड्यूल पर इससे पुराने पूरे चंक हटाता रहेगा"
    ),
    "TimescaleDB stops dropping old chunks automatically; chunks already dropped do not return": (
        "TimescaleDB पुराने चंक स्वतः हटाना बंद कर देगा; पहले ही हटाए गए चंक वापस नहीं आते"
    ),
    "TimescaleDB keeps compressing chunks older than this on its own schedule; compressed chunks stay readable": (
        "TimescaleDB अपने शेड्यूल पर इससे पुराने चंक कम्प्रेस करता रहेगा; कम्प्रेस किए गए चंक पठनीय रहते हैं"
    ),
    "TimescaleDB stops compressing chunks automatically; chunks already compressed stay compressed": (
        "TimescaleDB चंक स्वतः कम्प्रेस करना बंद कर देगा; पहले से कम्प्रेस चंक कम्प्रेस ही रहेंगे"
    ),
    "Other policy changes made here in this database wait until it commits, and so may a policy run starting meanwhile": (
        "इस डेटाबेस में यहाँ किए गए अन्य नीति परिवर्तन कमिट तक प्रतीक्षा करते हैं, और इस बीच शुरू होने वाला नीति रन भी प्रतीक्षा कर सकता है"
    ),
    "Review the retention policy plan before applying it": (
        "लागू करने से पहले रिटेंशन नीति योजना देखें"
    ),
    "Review the compression policy plan before applying it": (
        "लागू करने से पहले कम्प्रेशन नीति योजना देखें"
    ),
    "Retention policy set: TimescaleDB drops chunks older than {age} on its own schedule": (
        "रिटेंशन नीति सेट: TimescaleDB अपने शेड्यूल पर {age} से पुराने चंक हटाता है"
    ),
    "Retention policy removed; TimescaleDB no longer drops old chunks automatically": (
        "रिटेंशन नीति हटा दी गई; TimescaleDB अब पुराने चंक स्वतः नहीं हटाता"
    ),
    "Compression policy set: TimescaleDB compresses chunks older than {age} on its own schedule": (
        "कम्प्रेशन नीति सेट: TimescaleDB अपने शेड्यूल पर {age} से पुराने चंक कम्प्रेस करता है"
    ),
    "Compression policy removed; TimescaleDB no longer compresses chunks automatically": (
        "कम्प्रेशन नीति हटा दी गई; TimescaleDB अब चंक स्वतः कम्प्रेस नहीं करता"
    ),
    "This hypertable has several retention policy jobs; manage them with SQL": (
        "इस हाइपरटेबल में कई रिटेंशन नीति जॉब हैं; उन्हें SQL से प्रबंधित करें"
    ),
    "This hypertable has several compression policy jobs; manage them with SQL": (
        "इस हाइपरटेबल में कई कम्प्रेशन नीति जॉब हैं; उन्हें SQL से प्रबंधित करें"
    ),
    "The existing retention policy could not be read safely; manage it with SQL": (
        "मौजूदा रिटेंशन नीति सुरक्षित रूप से नहीं पढ़ी जा सकी; इसे SQL से प्रबंधित करें"
    ),
    "The existing compression policy could not be read safely; manage it with SQL": (
        "मौजूदा कम्प्रेशन नीति सुरक्षित रूप से नहीं पढ़ी जा सकी; इसे SQL से प्रबंधित करें"
    ),
    "TimescaleDB retention policy planning timed out": "TimescaleDB रिटेंशन नीति की योजना बनाने का समय समाप्त हो गया",
    "TimescaleDB compression policy planning timed out": "TimescaleDB कम्प्रेशन नीति की योजना बनाने का समय समाप्त हो गया",
    "TimescaleDB retention policy metadata could not be inspected safely": (
        "TimescaleDB रिटेंशन नीति मेटाडेटा सुरक्षित रूप से नहीं देखा जा सका"
    ),
    "TimescaleDB compression policy metadata could not be inspected safely": (
        "TimescaleDB कम्प्रेशन नीति मेटाडेटा सुरक्षित रूप से नहीं देखा जा सका"
    ),
    "Enable compression on this hypertable first": "पहले इस हाइपरटेबल पर कम्प्रेशन सक्षम करें",
    "This hypertable has no retention policy": "इस हाइपरटेबल में कोई रिटेंशन नीति नहीं है",
    "This hypertable has no compression policy": "इस हाइपरटेबल में कोई कम्प्रेशन नीति नहीं है",
    "Date dimensions require whole days, weeks, months or years": (
        "date आयामों के लिए पूरे दिन, सप्ताह, महीने या वर्ष आवश्यक हैं"
    ),
    "The existing retention policy is paused; remove it before setting a new one": (
        "मौजूदा रिटेंशन नीति रुकी हुई है; नई सेट करने से पहले इसे हटाएँ"
    ),
    "The existing compression policy is paused; remove it before setting a new one": (
        "मौजूदा कम्प्रेशन नीति रुकी हुई है; नई सेट करने से पहले इसे हटाएँ"
    ),
    # कंटीन्यूअस एग्रीगेट की रीफ़्रेश नीति।
    "Set refresh policy": "रीफ़्रेश नीति सेट करें",
    "Remove refresh policy": "रीफ़्रेश नीति हटाएँ",
    "Window starts": "विंडो का आरंभ",
    "How long ago the refreshed window begins": "रीफ़्रेश की गई विंडो कितने समय पहले शुरू होती है",
    "Window ends": "विंडो का अंत",
    "How long ago it ends; more recent than the start": "यह कितने समय पहले समाप्त होती है; आरंभ से अधिक नया",
    "Refresh every": "रीफ़्रेश अंतराल",
    "Set the refresh policy for {target}": "{target} के लिए रीफ़्रेश नीति सेट करें",
    "Remove the refresh policy from {target}": "{target} से रीफ़्रेश नीति हटाएँ",
    "Source hypertable: {source}": "स्रोत हाइपरटेबल: {source}",
    "No refresh policy exists yet": "अभी कोई रीफ़्रेश नीति नहीं है",
    "from the earliest data to the latest data": "सबसे पहले डेटा से नवीनतम डेटा तक",
    "from the earliest data to {end} ago": "सबसे पहले डेटा से {end} पहले तक",
    "from {start} ago to the latest data": "{start} पहले से नवीनतम डेटा तक",
    "from {start} ago to {end} ago": "{start} पहले से {end} पहले तक",
    "Removes job {job}, which refreshes {window} every {every}": (
        "जॉब {job} हटाता है, जो हर {every} में {window} रीफ़्रेश करता है"
    ),
    "Replaces job {job}, which refreshes {window} every {every}": (
        "जॉब {job} को बदलता है, जो हर {every} में {window} रीफ़्रेश करता है"
    ),
    "New policy: refresh from {start} ago to {end} ago, every {every}": (
        "नई नीति: {start} पहले से {end} पहले तक हर {every} में रीफ़्रेश करें"
    ),
    "The source hypertable has no retention policy": "स्रोत हाइपरटेबल में कोई रिटेंशन नीति नहीं है",
    "The source drops chunks older than {age}; the window starts after that": (
        "स्रोत {age} से पुराने चंक हटाता है; विंडो उसके बाद शुरू होती है"
    ),
    "The source drops chunks {chunks}; check that it keeps the raw data this window refreshes": (
        "स्रोत चंक {chunks} हटाता है; जाँचें कि यह इस विंडो द्वारा रीफ़्रेश किया जाने वाला कच्चा डेटा रखता है"
    ),
    "TimescaleDB stops refreshing this aggregate automatically; its materialized rows stay as they are": (
        "TimescaleDB इस एग्रीगेट को स्वतः रीफ़्रेश करना बंद कर देगा; इसकी मटीरियलाइज़्ड पंक्तियाँ जैसी हैं वैसी रहेंगी"
    ),
    "TimescaleDB keeps refreshing this window on its own schedule, after this session ends": (
        "इस सत्र के समाप्त होने के बाद TimescaleDB अपने शेड्यूल पर इस विंडो को रीफ़्रेश करता रहेगा"
    ),
    "This continuous aggregate has no refresh policy": "इस कंटीन्यूअस एग्रीगेट में कोई रीफ़्रेश नीति नहीं है",
    "Review the refresh policy plan before applying it": "लागू करने से पहले रीफ़्रेश नीति योजना देखें",
    "Refresh policy set: TimescaleDB refreshes this aggregate on its own schedule": (
        "रीफ़्रेश नीति सेट: TimescaleDB इस एग्रीगेट को अपने शेड्यूल पर रीफ़्रेश करता है"
    ),
    "Refresh policy removed; TimescaleDB no longer refreshes this aggregate automatically": (
        "रीफ़्रेश नीति हटा दी गई; TimescaleDB अब इस एग्रीगेट को स्वतः रीफ़्रेश नहीं करता"
    ),
    "The existing refresh policy is paused; remove it before setting a new one": (
        "मौजूदा रीफ़्रेश नीति रुकी हुई है; नई सेट करने से पहले इसे हटाएँ"
    ),
    "TimescaleDB refresh policy planning timed out": "TimescaleDB रीफ़्रेश नीति की योजना बनाने का समय समाप्त हो गया",
    "TimescaleDB refresh policy metadata could not be inspected safely": (
        "TimescaleDB रीफ़्रेश नीति मेटाडेटा सुरक्षित रूप से नहीं देखा जा सका"
    ),
    "This continuous aggregate has several refresh policy jobs; manage them with SQL": (
        "इस कंटीन्यूअस एग्रीगेट में कई रीफ़्रेश नीति जॉब हैं; उन्हें SQL से प्रबंधित करें"
    ),
    "The existing refresh policy could not be read safely; manage it with SQL": (
        "मौजूदा रीफ़्रेश नीति सुरक्षित रूप से नहीं पढ़ी जा सकी; इसे SQL से प्रबंधित करें"
    ),
    "Date dimensions require offsets in whole days, weeks, months or years": (
        "date आयामों में ऑफ़सेट पूरे दिन, सप्ताह, महीने या वर्ष में होना चाहिए"
    ),
    "The window must start further back than it ends": "विंडो का आरंभ उसके अंत से और पीछे होना चाहिए",
    "The window reaches data the source's retention policy drops (older than {age}); refreshing there would remove aggregated rows": (
        "विंडो उस डेटा तक पहुँचती है जिसे स्रोत की रिटेंशन नीति हटा देती है ({age} से पुराना); वहाँ रीफ़्रेश करने से एग्रीगेट की पंक्तियाँ हट जाएँगी"
    ),
    # कम्प्रेशन सेटिंग्स।
    "Configure compression": "कम्प्रेशन कॉन्फ़िगर करें",
    "Segment by": "सेगमेंट के अनुसार",
    "One column per line; leave empty for none": "प्रति पंक्ति एक कॉलम; कोई न हो तो खाली छोड़ें",
    "Order by": "क्रम के अनुसार",
    "One column per line, optionally followed by ASC or DESC and NULLS FIRST or NULLS LAST; the time column is added descending when neither list names it": (
        "प्रति पंक्ति एक कॉलम, वैकल्पिक रूप से ASC या DESC और NULLS FIRST या NULLS LAST के साथ; जब कोई सूची समय कॉलम का नाम नहीं देती, तो उसे अवरोही क्रम में जोड़ा जाता है"
    ),
    "TimescaleDB compression settings could not be inspected safely": (
        "TimescaleDB कम्प्रेशन सेटिंग्स सुरक्षित रूप से नहीं देखी जा सकीं"
    ),
    "Change the compression settings of {target}": "{target} की कम्प्रेशन सेटिंग्स बदलें",
    "Enable compression on {target}": "{target} पर कम्प्रेशन सक्षम करें",
    "Current segment by: {columns}": "वर्तमान सेगमेंट: {columns}",
    "Current segment by: none": "वर्तमान सेगमेंट: कोई नहीं",
    "Current order by: {columns}": "वर्तमान क्रम: {columns}",
    "Current order by: none": "वर्तमान क्रम: कोई नहीं",
    "Compression is not enabled yet": "कम्प्रेशन अभी सक्षम नहीं है",
    "New segment by: {columns}": "नया सेगमेंट: {columns}",
    "New segment by: none": "नया सेगमेंट: कोई नहीं",
    "New order by: {columns}": "नया क्रम: {columns}",
    "Already compressed chunks keep the settings they were compressed with": (
        "पहले से कम्प्रेस चंक वे सेटिंग्स रखते हैं जिनसे उन्हें कम्प्रेस किया गया था"
    ),
    "TimescaleDB recommends segmenting or ordering by the unique column {column}": (
        "TimescaleDB अद्वितीय कॉलम {column} द्वारा सेगमेंट या क्रम करने की सलाह देता है"
    ),
    "Review the compression settings plan before applying it": (
        "लागू करने से पहले कम्प्रेशन सेटिंग्स योजना देखें"
    ),
    "Compression settings changed; only chunks compressed from now on use them": (
        "कम्प्रेशन सेटिंग्स बदल गईं; अब से कम्प्रेस होने वाले चंक ही इन्हें उपयोग करेंगे"
    ),
    "Compression enabled; chunks are compressed by a compression policy or on request": (
        "कम्प्रेशन सक्षम; चंक कम्प्रेशन नीति द्वारा या अनुरोध पर कम्प्रेस होते हैं"
    ),
    "Nothing is compressed now; chunks are compressed later by a compression policy or on request": (
        "अभी कुछ भी कम्प्रेस नहीं है; चंक बाद में कम्प्रेशन नीति द्वारा या अनुरोध पर कम्प्रेस होंगे"
    ),
    "Only chunks compressed from now on use these settings; already compressed chunks keep theirs": (
        "अब से कम्प्रेस होने वाले चंक ही ये सेटिंग्स उपयोग करेंगे; पहले से कम्प्रेस चंक अपनी सेटिंग्स रखेंगे"
    ),
    "Locks this hypertable exclusively while the settings change; its reads and writes wait until it commits": (
        "सेटिंग्स बदलते समय इस हाइपरटेबल को विशेष रूप से लॉक करता है; इसके पढ़ने और लिखने कमिट तक प्रतीक्षा करते हैं"
    ),
    "Column \"{column}\" is listed more than once": "कॉलम “{column}” एक से अधिक बार सूचीबद्ध है",
    "List at most {count} segment-by columns": "अधिकतम {count} सेगमेंट कॉलम सूचीबद्ध करें",
    "List at most {count} order-by columns": "अधिकतम {count} क्रम कॉलम सूचीबद्ध करें",
    "Each line names one column": "प्रत्येक पंक्ति एक कॉलम का नाम देती है",
    "This hypertable has no column \"{column}\"": "इस हाइपरटेबल में कॉलम “{column}” नहीं है",
    "The current compression settings could not be read": "वर्तमान कम्प्रेशन सेटिंग्स पढ़ी नहीं जा सकीं",
    "TimescaleDB compression settings planning timed out": "TimescaleDB कम्प्रेशन सेटिंग्स की योजना बनाने का समय समाप्त हो गया",
    # टेबल बदलना।
    "Convert to hypertable": "हाइपरटेबल में बदलें",
    "The table becomes a hypertable, which DataPlayer cannot turn back into an ordinary table. Convert it?": (
        "टेबल हाइपरटेबल बन जाएगी, जिसे DataPlayer सामान्य टेबल में वापस नहीं बदल सकता। इसे बदलें?"
    ),
    "Time column": "समय कॉलम",
    "A timestamp or date column of this table": "इस टेबल का timestamp या date कॉलम",
    "Chunk interval": "चंक अंतराल",
    "The table could not be inspected safely for conversion": (
        "बदलाव के लिए टेबल सुरक्षित रूप से नहीं जाँची जा सकी"
    ),
    "Convert {target} into a hypertable": "{target} को हाइपरटेबल में बदलें",
    "Time column: {column} ({type})": "समय कॉलम: {column} ({type})",
    "Chunk interval: {interval}": "चंक अंतराल: {interval}",
    "The table is empty, and the conversion refuses if a row arrives before it runs": (
        "टेबल खाली है, और यदि बदलाव चलने से पहले कोई पंक्ति आ जाए तो वह अस्वीकार हो जाता है"
    ),
    "{column} becomes NOT NULL": "{column} NOT NULL हो जाएगा",
    "{column} becomes NOT NULL; a row without a time makes the conversion fail and roll back": (
        "{column} NOT NULL हो जाएगा; समय के बिना कोई पंक्ति बदलाव को विफल कर देगी और वह वापस लौट जाएगा"
    ),
    "An index on {column} alone already exists, so TimescaleDB adds none": (
        "{column} अकेले पर इंडेक्स पहले से मौजूद है, इसलिए TimescaleDB कोई नहीं जोड़ता"
    ),
    "TimescaleDB adds an index on {column}, newest first": (
        "TimescaleDB {column} पर इंडेक्स जोड़ता है, नवीनतम पहले"
    ),
    "The table keeps its name and identity and becomes a hypertable; DataPlayer cannot turn it back into an ordinary table": (
        "टेबल अपना नाम और पहचान रखती है और हाइपरटेबल बन जाती है; DataPlayer इसे सामान्य टेबल में वापस नहीं बदल सकता"
    ),
    "Locks this table exclusively for the conversion; its reads and writes wait until it commits": (
        "बदलाव के लिए इस टेबल को विशेष रूप से लॉक करता है; इसके पढ़ने और लिखने कमिट तक प्रतीक्षा करते हैं"
    ),
    "Review the conversion plan before applying it": "लागू करने से पहले बदलाव योजना देखें",
    "Converted to a hypertable; rows added from now on are stored in chunks": (
        "हाइपरटेबल में बदल दिया गया; अब से जोड़ी गई पंक्तियाँ चंक में संग्रहीत होंगी"
    ),
    "Choose an existing ordinary table": "कोई मौजूदा सामान्य टेबल चुनें",
    "This table is already a hypertable": "यह टेबल पहले से हाइपरटेबल है",
    "Foreign keys between this table and a hypertable are not supported": (
        "इस टेबल और हाइपरटेबल के बीच फ़ॉरेन की समर्थित नहीं हैं"
    ),
    "This table has no timestamp or date column to partition by": (
        "इस टेबल में विभाजन के लिए कोई timestamp या date कॉलम नहीं है"
    ),
    "This table has no timestamp, date or integer column to partition by": (
        "इस टेबल में विभाजन के लिए कोई timestamp, date या पूर्णांक कॉलम नहीं है"
    ),
    "This table is not empty; only empty tables are converted here": (
        "यह टेबल खाली नहीं है; यहाँ केवल खाली टेबलें बदली जाती हैं"
    ),
    "This table has too many indexes to inspect": "इस टेबल में जाँच के लिए बहुत अधिक इंडेक्स हैं",
    "The TimescaleDB conversion API is split across schemas": "TimescaleDB कन्वर्ज़न API कई स्कीमाओं में विभाजित है",
    "TimescaleDB conversion planning timed out": "TimescaleDB कन्वर्ज़न की योजना बनाने का समय समाप्त हो गया",
    "Only the table's owner can convert it": "केवल टेबल का स्वामी ही इसे बदल सकता है",
    "This connection may not read the table": "यह कनेक्शन टेबल नहीं पढ़ सकता",
    "Partitioned tables cannot become hypertables": "विभाजित टेबलें हाइपरटेबल नहीं बन सकतीं",
    "Choose an ordinary table": "सामान्य टेबल चुनें",
    "Tables with NO INHERIT constraints cannot become hypertables": (
        "NO INHERIT कंस्ट्रेंट वाली टेबलें हाइपरटेबल नहीं बन सकतीं"
    ),
    "Tables that use inheritance cannot become hypertables": (
        "इनहेरिटेंस का उपयोग करने वाली टेबलें हाइपरटेबल नहीं बन सकतीं"
    ),
    "Only logged tables can become hypertables": "केवल लॉग्ड टेबलें हाइपरटेबल बन सकती हैं",
    "Tables with rules cannot become hypertables": "नियमों वाली टेबलें हाइपरटेबल नहीं बन सकतीं",
    "Choose a column this table can be partitioned by: {choices}": (
        "वह कॉलम चुनें जिससे इस टेबल को विभाजित किया जा सके: {choices}"
    ),
    "Unique index \"{index}\" must include \"{column}\", which partitions the table": (
        "अद्वितीय इंडेक्स “{index}” में “{column}” शामिल होना चाहिए, जो टेबल को विभाजित करता है"
    ),
    "An integer or UUID column is converted from Hypertable settings": (
        "पूर्णांक या UUID कॉलम “हाइपरटेबल सेटिंग्स” से बदला जाता है"
    ),
    "Date columns require whole days or weeks": "date कॉलम के लिए पूरे दिन या सप्ताह आवश्यक हैं",
    # चंक कम्प्रेस और डीकम्प्रेस करना।
    "Compress chunks": "चंक कम्प्रेस करें",
    "Decompress chunks": "चंक डीकम्प्रेस करें",
    "TimescaleDB chunk metadata could not be inspected safely": (
        "TimescaleDB चंक मेटाडेटा सुरक्षित रूप से नहीं देखा जा सका"
    ),
    "TimescaleDB chunk metadata could not be read": "TimescaleDB चंक मेटाडेटा पढ़ा नहीं जा सका",
    "TimescaleDB chunk planning timed out": "TimescaleDB चंक संचालन की योजना बनाने का समय समाप्त हो गया",
    "Compress 1 chunk of {target} as a job": "{target} का 1 चंक जॉब के रूप में कम्प्रेस करें",
    "Compress {count} chunks of {target} as a job": "{target} के {count} चंक जॉब के रूप में कम्प्रेस करें",
    "Decompress 1 chunk of {target} as a job": "{target} का 1 चंक जॉब के रूप में डीकम्प्रेस करें",
    "Decompress {count} chunks of {target} as a job": "{target} के {count} चंक जॉब के रूप में डीकम्प्रेस करें",
    "Already compressed and left as they are: {count}": "पहले से कम्प्रेस और जैसे हैं वैसे छोड़े गए: {count}",
    "Already decompressed and left as they are: {count}": "पहले से डीकम्प्रेस और जैसे हैं वैसे छोड़े गए: {count}",
    "Compressed chunks stay readable; queries and writes touching a chunk may wait while it is rewritten": (
        "कम्प्रेस किए गए चंक पठनीय रहते हैं; किसी चंक को फिर से लिखे जाने के दौरान उसे छूने वाली क्वेरी और लेखन प्रतीक्षा कर सकते हैं"
    ),
    "Decompressed chunks take more space; a compression policy may compress them again on its own schedule": (
        "डीकम्प्रेस किए गए चंक अधिक जगह लेते हैं; कम्प्रेशन नीति उन्हें अपने शेड्यूल पर फिर कम्प्रेस कर सकती है"
    ),
    "Each chunk is converted in its own transaction; cancelling keeps the chunks already converted": (
        "प्रत्येक चंक अपने लेन-देन में बदला जाता है; रद्द करने पर पहले से बदले चंक बने रहते हैं"
    ),
    "The hypertable could not be found; nothing was converted": "हाइपरटेबल नहीं मिला; कुछ भी नहीं बदला गया",
    "Every whole chunk inside this window is already compressed": "इस विंडो के भीतर हर पूरा चंक पहले से कम्प्रेस है",
    "No whole chunk inside this window is compressed": "इस विंडो के भीतर कोई पूरा चंक कम्प्रेस नहीं है",
    "No whole chunk lies inside this window": "इस विंडो के भीतर कोई पूरा चंक नहीं है",
    "More than {count} chunks lie inside this window; narrow it": (
        "इस विंडो के भीतर {count} से अधिक चंक हैं; इसे छोटा करें"
    ),
    "This chunk is in use; nothing was converted": "यह चंक उपयोग में है; कुछ भी नहीं बदला गया",
    "The source cancelled converting this chunk after its fifteen minutes; it was rolled back": (
        "स्रोत ने पंद्रह मिनट बाद इस चंक को बदलना रद्द कर दिया; इसे वापस लौटा दिया गया"
    ),
    "This connection may not convert this chunk": "यह कनेक्शन इस चंक को नहीं बदल सकता",
    "The connection was lost while this chunk was being converted; its outcome is unknown": (
        "इस चंक को बदलते समय कनेक्शन टूट गया; परिणाम अज्ञात है"
    ),
    "The source could not be reached; nothing was converted": "स्रोत तक नहीं पहुँचा जा सका; कुछ भी नहीं बदला गया",
    "The hypertable could not be checked in time; nothing was converted": (
        "हाइपरटेबल समय पर नहीं जाँचा जा सका; कुछ भी नहीं बदला गया"
    ),
    "The hypertable could not be checked safely; nothing was converted": (
        "हाइपरटेबल सुरक्षित रूप से नहीं जाँचा जा सका; कुछ भी नहीं बदला गया"
    ),
    "The hypertable or its TimescaleDB API changed after review; nothing was converted": (
        "देखने के बाद हाइपरटेबल या उसका TimescaleDB API बदल गया; कुछ भी नहीं बदला गया"
    ),
    "This chunk is no longer part of the hypertable": "यह चंक अब हाइपरटेबल का हिस्सा नहीं है",
    "The source could not be reached or prepared; nothing was converted": (
        "स्रोत तक नहीं पहुँचा जा सका या उसे तैयार नहीं किया जा सका; कुछ भी नहीं बदला गया"
    ),
    "The source refused to convert this chunk": "स्रोत ने इस चंक को बदलने से इनकार कर दिया",
    # चंक रखरखाव।
    "Drop chunks": "चंक हटाएँ",
    "Drop these chunks and every row in them? This cannot be undone.": (
        "क्या इन चंक और इनमें मौजूद हर पंक्ति को हटाना है? इसे पूर्ववत नहीं किया जा सकता।"
    ),
    "Detach chunks": "चंक अलग करें",
    "Merge chunks": "चंक मिलाएँ",
    "Merge chunks, reads going on": "चंक मिलाएँ, पढ़ना जारी रहे",
    "Move chunks to a tablespace": "चंक को टेबलस्पेस में ले जाएँ",
    "Reorder chunks by an index": "चंक को इंडेक्स के अनुसार पुनः क्रमित करें",
    "Split a chunk": "चंक विभाजित करें",
    "Attach a table as a chunk": "टेबल को चंक के रूप में संलग्न करें",
    "Drop chunks…": "चंक हटाएँ…",
    "Move chunks to a tablespace…": "चंक को टेबलस्पेस में ले जाएँ…",
    "Reorder chunks by an index…": "चंक को इंडेक्स के अनुसार पुनः क्रमित करें…",
    "Detach chunks…": "चंक अलग करें…",
    "Merge chunks…": "चंक मिलाएँ…",
    "Merge chunks, reads going on…": "चंक मिलाएँ, पढ़ना जारी रहे…",
    "Tablespace": "टेबलस्पेस",
    "An existing tablespace this connection may create in": (
        "एक मौजूदा टेबलस्पेस जिसमें यह कनेक्शन बना सकता है"
    ),
    "Order rows by index": "पंक्तियों को इंडेक्स से क्रमित करें",
    "Leave empty for the index on the time column": "समय कॉलम के इंडेक्स के लिए खाली छोड़ें",
    "Index tablespace": "इंडेक्स टेबलस्पेस",
    "Leave empty to move the indexes with the chunk": "इंडेक्स को चंक के साथ ले जाने के लिए खाली छोड़ें",
    "Index": "इंडेक्स",
    "An index of this hypertable to order rows by": "इस हाइपरटेबल का एक इंडेक्स जिससे पंक्तियाँ क्रमित करनी हैं",
    "Split at": "यहाँ विभाजित करें",
    "With its time zone; the chunk holding this instant is split at it": (
        "समय क्षेत्र सहित; इस क्षण को रखने वाला चंक यहाँ विभाजित होता है"
    ),
    "Schema of the table": "टेबल का स्कीमा",
    "Table": "टेबल",
    "A table with the hypertable's columns, such as a detached chunk": (
        "हाइपरटेबल के कॉलम वाली टेबल, जैसे कोई अलग किया गया चंक"
    ),
    "Covering from": "यहाँ से कवर करते हुए",
    "Until": "तक",
    "Either a window or picked chunks, not both": "या तो विंडो या चुने गए चंक, दोनों नहीं",
    "Give where the window ends": "बताएँ कि विंडो कहाँ समाप्त होती है",
    "With the chunk": "चंक के साथ",
    "The index on the time column": "समय कॉलम पर इंडेक्स",
    "A value of \"{column}\", the {type} column the hypertable is partitioned by": (
        "“{column}” का एक मान, वह {type} कॉलम जिससे हाइपरटेबल विभाजित है"
    ),
    "A value of \"{column}\", the {type} column the hypertable is partitioned by; leave empty for every earlier chunk": (
        "“{column}” का एक मान, वह {type} कॉलम जिससे हाइपरटेबल विभाजित है; सभी पहले के चंक के लिए खाली छोड़ें"
    ),
    "A value of \"{column}\", the {type} column the hypertable is partitioned by; the chunk holding it is split at it": (
        "“{column}” का एक मान, वह {type} कॉलम जिससे हाइपरटेबल विभाजित है; इसे रखने वाला चंक यहाँ विभाजित होता है"
    ),
    "Drop 1 chunk of {target} as a job": "{target} का 1 चंक जॉब के रूप में हटाएँ",
    "Drop {count} chunks of {target} as a job": "{target} के {count} चंक जॉब के रूप में हटाएँ",
    "Move 1 chunk of {target} as a job": "{target} का 1 चंक जॉब के रूप में ले जाएँ",
    "Move {count} chunks of {target} as a job": "{target} के {count} चंक जॉब के रूप में ले जाएँ",
    "Reorder 1 chunk of {target} as a job": "{target} का 1 चंक जॉब के रूप में पुनः क्रमित करें",
    "Reorder {count} chunks of {target} as a job": "{target} के {count} चंक जॉब के रूप में पुनः क्रमित करें",
    "Detach 1 chunk of {target} as a job": "{target} का 1 चंक जॉब के रूप में अलग करें",
    "Detach {count} chunks of {target} as a job": "{target} के {count} चंक जॉब के रूप में अलग करें",
    "Merge {count} chunks of {target} into one as a job": "{target} के {count} चंक को जॉब के रूप में एक में मिलाएँ",
    "Split {chunk} at {point} as a job": "{chunk} को {point} पर जॉब के रूप में विभाजित करें",
    "Attach {table} to {target} as a chunk as a job": "{table} को जॉब के रूप में {target} में चंक के रूप में संलग्न करें",
    "Exactly the chunks picked in the Chunks report, each read again by name": (
        "“चंक” रिपोर्ट में चुने गए ठीक वही चंक, हर एक को नाम से फिर पढ़ा जाता है"
    ),
    "Left as they are, already in {tablespace}: {count}": "जैसे हैं वैसे छोड़े गए, पहले से {tablespace} में: {count}",
    "Left as they are, compressed, which reorder_chunk does not rewrite: {count}": (
        "जैसे हैं वैसे छोड़े गए, कम्प्रेस, जिन्हें reorder_chunk फिर से नहीं लिखता: {count}"
    ),
    "Left as they are, compressed; TimescaleDB detaches only uncompressed chunks: {count}": (
        "जैसे हैं वैसे छोड़े गए, कम्प्रेस; TimescaleDB केवल अकम्प्रेस चंक अलग करता है: {count}"
    ),
    "Left as they are: {count}": "जैसे हैं वैसे छोड़े गए: {count}",
    "Every row in these chunks is deleted; each chunk is dropped by name, never by an age read when the job runs": (
        "इन चंक की हर पंक्ति हटा दी जाती है; प्रत्येक चंक नाम से हटाया जाता है, जॉब चलने पर कभी पढ़ी गई आयु से नहीं"
    ),
    "Each chunk becomes an ordinary table under its own name and leaves the hypertable's queries; Detached chunks lists it, and Attach chunk brings it back": (
        "प्रत्येक चंक अपने नाम से सामान्य टेबल बन जाता है और हाइपरटेबल की क्वेरी से बाहर हो जाता है; “अलग किए गए चंक” उसे सूचीबद्ध करता है, और “चंक संलग्न करें” उसे वापस लाता है"
    ),
    "The chunks become one, covering their whole range; the table is locked while they merge": (
        "चंक एक हो जाते हैं और उनकी पूरी सीमा कवर करते हैं; मिलने के दौरान टेबल लॉक रहती है"
    ),
    "The chunks become one, covering their whole range; reads go on meanwhile, writes to them wait": (
        "चंक एक हो जाते हैं और उनकी पूरी सीमा कवर करते हैं; इस दौरान पढ़ना जारी रहता है, उनमें लिखना प्रतीक्षा करता है"
    ),
    "Each chunk is copied to the tablespace and the old copy removed; reads and writes to it wait meanwhile": (
        "प्रत्येक चंक टेबलस्पेस में कॉपी किया जाता है और पुरानी प्रति हटाई जाती है; इस दौरान उस पर पढ़ना और लिखना प्रतीक्षा करते हैं"
    ),
    "Each chunk is rewritten in the index's order, which speeds reads along it; reads and writes wait meanwhile": (
        "प्रत्येक चंक इंडेक्स के क्रम में फिर से लिखा जाता है, जिससे उसके अनुसार पढ़ने की गति बढ़ती है; इस दौरान पढ़ना और लिखना प्रतीक्षा करते हैं"
    ),
    "The chunk becomes two, divided at this point; the table is locked while it splits": (
        "चंक इस बिंदु पर दो में विभाजित हो जाता है; विभाजन के दौरान टेबल लॉक रहती है"
    ),
    "Its rows join the hypertable's queries; TimescaleDB refuses a table whose columns or rows do not fit": (
        "इसकी पंक्तियाँ हाइपरटेबल की क्वेरी में शामिल हो जाती हैं; जिस टेबल के कॉलम या पंक्तियाँ मेल नहीं खातीं, TimescaleDB उसे अस्वीकार कर देता है"
    ),
    "The hypertable could not be found; nothing was changed": "हाइपरटेबल नहीं मिला; कुछ भी नहीं बदला गया",
    "This hypertable is partitioned by the integer column \"{column}\"; give its values, not instants": (
        "यह हाइपरटेबल पूर्णांक कॉलम “{column}” से विभाजित है; इसके मान दें, क्षण नहीं"
    ),
    "This hypertable is partitioned by time on \"{column}\"; give instants, not numbers": (
        "यह हाइपरटेबल “{column}” पर समय से विभाजित है; क्षण दें, संख्याएँ नहीं"
    ),
    "Chunks of a hypertable partitioned by hash on {columns} are not merged here: which partition a chunk is in is not public, so the result could not be checked first": (
        "यहाँ {columns} पर हैश से विभाजित हाइपरटेबल के चंक नहीं मिलाए जाते: कौन-सा चंक किस विभाजन में है यह सार्वजनिक नहीं है, इसलिए परिणाम पहले नहीं जाँचा जा सका"
    ),
    "Chunks of a hypertable partitioned by hash on {columns} are not attached here: which partition a chunk is in is not public, so the result could not be checked first": (
        "यहाँ {columns} पर हैश से विभाजित हाइपरटेबल के चंक संलग्न नहीं किए जाते: कौन-सा चंक किस विभाजन में है यह सार्वजनिक नहीं है, इसलिए परिणाम पहले नहीं जाँचा जा सका"
    ),
    "TimescaleDB splits no chunk of a hypertable partitioned by hash as well as by time": (
        "TimescaleDB समय के साथ-साथ हैश से भी विभाजित हाइपरटेबल का कोई चंक विभाजित नहीं करता"
    ),
    "Pick at least one chunk": "कम से कम एक चंक चुनें",
    "Pick at most {count} chunks at a time": "एक बार में अधिकतम {count} चंक चुनें",
    "\"{name}\" is not a chunk of this hypertable any more": "“{name}” अब इस हाइपरटेबल का चंक नहीं है",
    "Tablespace \"{name}\" does not exist or this connection may not create in it": (
        "टेबलस्पेस “{name}” मौजूद नहीं है या यह कनेक्शन इसमें नहीं बना सकता"
    ),
    "This hypertable has no index \"{index}\"": "इस हाइपरटेबल में इंडेक्स “{index}” नहीं है",
    "Every whole chunk inside this window is already in {tablespace}": "इस विंडो का हर पूरा चंक पहले से {tablespace} में है",
    "Every picked chunk is already in {tablespace}": "हर चुना गया चंक पहले से {tablespace} में है",
    "Every whole chunk inside this window is compressed, which reorder_chunk does not rewrite": (
        "इस विंडो का हर पूरा चंक कम्प्रेस है, जिसे reorder_chunk फिर से नहीं लिखता"
    ),
    "Every picked chunk is compressed, which reorder_chunk does not rewrite": (
        "हर चुना गया चंक कम्प्रेस है, जिसे reorder_chunk फिर से नहीं लिखता"
    ),
    "Every whole chunk inside this window is compressed; TimescaleDB detaches only uncompressed chunks": (
        "इस विंडो का हर पूरा चंक कम्प्रेस है; TimescaleDB केवल अकम्प्रेस चंक अलग करता है"
    ),
    "Every picked chunk is compressed; TimescaleDB detaches only uncompressed chunks": (
        "हर चुना गया चंक कम्प्रेस है; TimescaleDB केवल अकम्प्रेस चंक अलग करता है"
    ),
    "Name an index: moving a chunk rewrites it in an index's order": (
        "इंडेक्स का नाम दें: चंक ले जाने पर उसे इंडेक्स के क्रम में फिर से लिखा जाता है"
    ),
    "A merge needs at least two chunks": "मिलाने के लिए कम से कम दो चंक आवश्यक हैं",
    "Chunks \"{before}\" and \"{after}\" are not adjacent; choose chunks that touch": (
        "चंक “{before}” और “{after}” सटे हुए नहीं हैं; ऐसे चंक चुनें जो एक-दूसरे से जुड़े हों"
    ),
    "TimescaleDB {version} cannot merge compressed chunks; decompress them first": (
        "TimescaleDB {version} कम्प्रेस चंक नहीं मिला सकता; पहले उन्हें डीकम्प्रेस करें"
    ),
    "No chunk holds this point strictly inside its range": "कोई चंक इस बिंदु को अपनी सीमा के भीतर पूरी तरह नहीं रखता",
    "There is no table \"{schema}\".\"{table}\"": "टेबल “{schema}”.“{table}” मौजूद नहीं है",
    "Only an ordinary table can become a chunk": "केवल सामान्य टेबल ही चंक बन सकती है",
    "Only the table's owner can attach it": "केवल टेबल का स्वामी ही इसे संलग्न कर सकता है",
    "A hypertable cannot become a chunk": "हाइपरटेबल चंक नहीं बन सकता",
    "This table is already a chunk": "यह टेबल पहले से चंक है",
    "A table that uses inheritance cannot become a chunk": "इनहेरिटेंस का उपयोग करने वाली टेबल चंक नहीं बन सकती",
    "Chunk \"{name}\" already covers part of this range": "चंक “{name}” पहले से इस सीमा का कुछ हिस्सा कवर करता है",
    "The range is empty once read in the column's type": "कॉलम के प्रकार में पढ़ने पर सीमा खाली है",
    "This chunk is in use; nothing was changed": "यह चंक उपयोग में है; कुछ भी नहीं बदला गया",
    "The source cancelled this unit after its fifteen minutes; it was rolled back": (
        "स्रोत ने पंद्रह मिनट बाद इस इकाई को रद्द कर दिया; इसे वापस लौटा दिया गया"
    ),
    "This connection may not change this chunk": "यह कनेक्शन इस चंक को नहीं बदल सकता",
    "The connection was lost while this unit was running; its outcome is unknown": (
        "इस इकाई के चलते समय कनेक्शन टूट गया; परिणाम अज्ञात है"
    ),
    "The hypertable could not be checked in time; nothing was changed": (
        "हाइपरटेबल समय पर नहीं जाँचा जा सका; कुछ भी नहीं बदला गया"
    ),
    "The hypertable or its chunks changed after review; nothing was changed": (
        "देखने के बाद हाइपरटेबल या उसके चंक बदल गए; कुछ भी नहीं बदला गया"
    ),
    "The hypertable could not be checked safely; nothing was changed": (
        "हाइपरटेबल सुरक्षित रूप से नहीं जाँचा जा सका; कुछ भी नहीं बदला गया"
    ),
    "The source could not be reached; nothing was changed": "स्रोत तक नहीं पहुँचा जा सका; कुछ भी नहीं बदला गया",
    "The table to attach is gone; nothing was changed": "संलग्न करने वाली टेबल चली गई; कुछ भी नहीं बदला गया",
    "This chunk was compressed after review; it was left as it is": (
        "देखने के बाद यह चंक कम्प्रेस हो गया; इसे जैसा है वैसा छोड़ दिया गया"
    ),
    "These chunks changed after review; nothing was merged": "देखने के बाद ये चंक बदल गए; कुछ भी नहीं मिलाया गया",
    "The index to order rows by is gone; nothing was changed": (
        "पंक्तियाँ क्रमित करने वाला इंडेक्स चला गया; कुछ भी नहीं बदला गया"
    ),
    "The source could not be reached or prepared; nothing was changed": (
        "स्रोत तक नहीं पहुँचा जा सका या उसे तैयार नहीं किया जा सका; कुछ भी नहीं बदला गया"
    ),
    "The source refused this unit; nothing was changed": "स्रोत ने इस इकाई को अस्वीकार कर दिया; कुछ भी नहीं बदला गया",
    "This is not offered over these rows": "इन पंक्तियों पर यह उपलब्ध नहीं है",
    "A chunk is named by its schema and its name": "चंक को उसके स्कीमा और नाम से पहचाना जाता है",
    "The picked chunks belong to {count} hypertables; pick chunks of one": (
        "चुने गए चंक {count} हाइपरटेबल के हैं; एक ही के चंक चुनें"
    ),
    "Some picked rows are not chunks any more; read the report again": (
        "कुछ चुनी गई पंक्तियाँ अब चंक नहीं हैं; रिपोर्ट फिर से पढ़ें"
    ),
    # किसी कॉलम से चंक छोड़ना।
    "Skip chunks by a column": "किसी कॉलम से चंक छोड़ें",
    "Stop skipping chunks by a column": "किसी कॉलम से चंक छोड़ना बंद करें",
    "Column": "कॉलम",
    "An integer, date or timestamp column queries filter on": "एक पूर्णांक, date या timestamp कॉलम जिस पर क्वेरी फ़िल्टर करती है",
    "The hypertable could not be inspected safely": "हाइपरटेबल सुरक्षित रूप से नहीं जाँचा जा सका",
    "TimescaleDB keeps ranges only of integer, date and timestamp columns, not of \"{column}\" ({type})": (
        "TimescaleDB केवल पूर्णांक, date और timestamp कॉलम की सीमाएँ रखता है, “{column}” ({type}) की नहीं"
    ),
    "Planning chunk skipping timed out": "चंक छोड़ने की योजना बनाने का समय समाप्त हो गया",
    "Chunks record the range of {column} as they are compressed, and a query filtering on it skips the chunks outside": (
        "चंक कम्प्रेस होते समय {column} की सीमा दर्ज करते हैं, और उस पर फ़िल्टर करने वाली क्वेरी बाहर के चंक छोड़ देती है"
    ),
    "Chunks stop recording the range of {column}, if they did": (
        "चंक {column} की सीमा दर्ज करना बंद कर देते हैं, यदि वे करते थे"
    ),
    "Changes nothing if it already holds: TimescaleDB keeps which columns record ranges where this application does not read": (
        "यदि पहले से ऐसा है तो कुछ नहीं बदलता: जहाँ यह एप्लिकेशन नहीं पढ़ता, वहाँ TimescaleDB यह बनाए रखता है कि कौन-से कॉलम सीमाएँ दर्ज करते हैं"
    ),
    "timescaledb.enable_chunk_skipping is off for this connection; queries use the ranges only in sessions that turn it on": (
        "इस कनेक्शन के लिए timescaledb.enable_chunk_skipping बंद है; क्वेरी इन सीमाओं का उपयोग केवल उन सत्रों में करती हैं जो इसे चालू करते हैं"
    ),
    "Skip chunks by {column} on {target}": "{target} पर {column} से चंक छोड़ें",
    "Stop skipping chunks by {column} on {target}": "{target} पर {column} से चंक छोड़ना बंद करें",
    "Review the chunk skipping plan before applying it": "लागू करने से पहले चंक छोड़ने की योजना देखें",
    "Chunk skipping turned on": "चंक छोड़ना चालू किया गया",
    "Chunk skipping turned off": "चंक छोड़ना बंद किया गया",
    # हाइपरटेबल सेटिंग्स: हाइपरटेबल पढ़ना।
    "Hypertable settings": "हाइपरटेबल सेटिंग्स",
    "Reading the hypertable timed out": "हाइपरटेबल पढ़ने का समय समाप्त हो गया",
    "Job {job} drops chunks {chunks}, every {every}": "जॉब {job} हर {every} चंक {chunks} हटाता है",
    "Job {job} drops chunks {chunks}, every {every}; paused": (
        "जॉब {job} हर {every} चंक {chunks} हटाता है; रुका हुआ"
    ),
    "Job {job} compresses chunks {chunks}, every {every}": "जॉब {job} हर {every} चंक {chunks} कम्प्रेस करता है",
    "Job {job} compresses chunks {chunks}, every {every}; paused": (
        "जॉब {job} हर {every} चंक {chunks} कम्प्रेस करता है; रुका हुआ"
    ),
    "Job {job} reorders chunks by {index}": "जॉब {job} चंक को {index} से पुनः क्रमित करता है",
    "Job {job} reorders chunks by {index}; paused": "जॉब {job} चंक को {index} से पुनः क्रमित करता है; रुका हुआ",
    "Job {job} reorders chunks by an index this editor cannot read": (
        "जॉब {job} चंक को ऐसे इंडेक्स से पुनः क्रमित करता है जिसे यह संपादक नहीं पढ़ सकता"
    ),
    "Job {job} reorders chunks by an index this editor cannot read; paused": (
        "जॉब {job} चंक को ऐसे इंडेक्स से पुनः क्रमित करता है जिसे यह संपादक नहीं पढ़ सकता; रुका हुआ"
    ),
    "The current sparse indexes could not be read": "वर्तमान स्पॉर्स इंडेक्स पढ़े नहीं जा सके",
    "This hypertable has a sparse index of a kind this editor does not know; manage it with SQL": (
        "इस हाइपरटेबल में ऐसे प्रकार का स्पॉर्स इंडेक्स है जिसे यह संपादक नहीं जानता; इसे SQL से प्रबंधित करें"
    ),
    "The current columnstore settings could not be read": (
        "वर्तमान कॉलमस्टोर सेटिंग्स पढ़ी नहीं जा सकीं"
    ),
    "This hypertable merges compressed chunks by a time interval; manage it with SQL": (
        "यह हाइपरटेबल कम्प्रेस चंक को समय अंतराल से मिलाता है; इसे SQL से प्रबंधित करें"
    ),
    "This hypertable has several compaction policy jobs; manage them with SQL": (
        "इस हाइपरटेबल में कई कम्पैक्शन नीति जॉब हैं; उन्हें SQL से प्रबंधित करें"
    ),
    "This hypertable has several reorder policy jobs; manage them with SQL": (
        "इस हाइपरटेबल में कई पुनःक्रमण नीति जॉब हैं; उन्हें SQL से प्रबंधित करें"
    ),
    "The existing reorder policy could not be read safely; manage it with SQL": (
        "मौजूदा पुनःक्रमण नीति सुरक्षित रूप से नहीं पढ़ी जा सकी; इसे SQL से प्रबंधित करें"
    ),
    "TimescaleDB {version} partitions by UUIDv7 only partly; it is edited here from 2.25": (
        "TimescaleDB {version} UUIDv7 से केवल आंशिक रूप से विभाजित करता है; इसे यहाँ 2.25 से संपादित किया जा सकता है"
    ),
    "Only timestamp, date, UUIDv7 and integer time dimensions are edited here": (
        "यहाँ केवल timestamp, date, UUIDv7 और पूर्णांक समय आयाम संपादित किए जाते हैं"
    ),
    "The current chunk interval could not be read": "वर्तमान चंक अंतराल पढ़ा नहीं जा सका",
    "Only hash dimensions beside the time dimension are edited here": (
        "यहाँ केवल समय आयाम के साथ हैश आयाम संपादित किए जाते हैं"
    ),
    "The hypertable's chunks and tablespaces could not be read": (
        "हाइपरटेबल के चंक और टेबलस्पेस पढ़े नहीं जा सके"
    ),
    "This connection may not create functions in schema \"{schema}\"": (
        "यह कनेक्शन स्कीमा “{schema}” में फ़ंक्शन नहीं बना सकता"
    ),
    "A function named \"{name}\" already exists; choose it from the list or another name": (
        "“{name}” नाम का फ़ंक्शन पहले से मौजूद है; सूची से उसे चुनें या दूसरा नाम चुनें"
    ),
    "A chunk interval of an integer column is a number of its values": "पूर्णांक कॉलम का चंक अंतराल उसके मानों की संख्या है",
    "A chunk interval of a {type} column is at most {count}": "{type} कॉलम का चंक अंतराल अधिकतम {count} है",
    "A chunk interval is counted in minutes, hours, days or weeks": (
        "चंक अंतराल मिनट, घंटे, दिन या सप्ताह में गिना जाता है"
    ),
    # हाइपरटेबल सेटिंग्स: परिवर्तन की योजना बनाना।
    "Locks this hypertable exclusively while it changes; its reads and writes wait until it commits": (
        "बदलते समय इस हाइपरटेबल को विशेष रूप से लॉक करता है; इसके पढ़ने और लिखने कमिट तक प्रतीक्षा करते हैं"
    ),
    "Other changes to this hypertable's settings wait until it commits": (
        "इस हाइपरटेबल की सेटिंग्स में अन्य परिवर्तन कमिट तक प्रतीक्षा करते हैं"
    ),
    "A chunk interval of this hypertable is counted in days or weeks": (
        "इस हाइपरटेबल का चंक अंतराल दिन या सप्ताह में गिना जाता है"
    ),
    "A chunk interval of this hypertable is counted in minutes or hours or days or weeks": (
        "इस हाइपरटेबल का चंक अंतराल मिनट, घंटे, दिन या सप्ताह में गिना जाता है"
    ),
    "A chunk interval of this column is counted in days or weeks": (
        "इस कॉलम का चंक अंतराल दिन या सप्ताह में गिना जाता है"
    ),
    "A chunk interval of this column is counted in minutes or hours or days or weeks": (
        "इस कॉलम का चंक अंतराल मिनट, घंटे, दिन या सप्ताह में गिना जाता है"
    ),
    "Column \"{column}\" has a type that cannot be used as a hash dimension": (
        "कॉलम “{column}” का प्रकार हैश आयाम के रूप में उपयोग नहीं किया जा सकता"
    ),
    "Column \"{column}\" has a type that cannot be used as a minmax sparse index": (
        "कॉलम “{column}” का प्रकार minmax स्पॉर्स इंडेक्स के रूप में उपयोग नहीं किया जा सकता"
    ),
    "Column \"{column}\" has a type that cannot be used as a segment column": (
        "कॉलम “{column}” का प्रकार सेगमेंट कॉलम के रूप में उपयोग नहीं किया जा सकता"
    ),
    "Column \"{column}\" has a type that cannot be used as an order column": (
        "कॉलम “{column}” का प्रकार क्रम कॉलम के रूप में उपयोग नहीं किया जा सकता"
    ),
    "TimescaleDB cannot remove the hash dimension on \"{column}\"": (
        "TimescaleDB “{column}” पर हैश आयाम नहीं हटा सकता"
    ),
    "A hash dimension can only be added while the hypertable holds no chunks": (
        "हैश आयाम तभी जोड़ा जा सकता है जब हाइपरटेबल में कोई चंक न हो"
    ),
    "The time column cannot also be a hash dimension": "समय कॉलम साथ में हैश आयाम नहीं हो सकता",
    "Unique key \"{key}\" must include \"{column}\" before it can be a hash dimension": (
        "हैश आयाम बनने से पहले अद्वितीय कुंजी “{key}” में “{column}” शामिल होना चाहिए"
    ),
    "TimescaleDB {version} has no sparse indexes; they arrived in 2.22": (
        "TimescaleDB {version} में स्पॉर्स इंडेक्स नहीं हैं; वे 2.22 में आए"
    ),
    "Column \"{column}\" has the same sparse index twice": "कॉलम “{column}” में वही स्पॉर्स इंडेक्स दो बार है",
    "Sparse indexes need the order to be named; choose the columns to order by": (
        "स्पॉर्स इंडेक्स के लिए क्रम निर्दिष्ट करना आवश्यक है; क्रम के लिए कॉलम चुनें"
    ),
    "Column \"{column}\" is listed more than once in the columnstore settings": (
        "कॉलमस्टोर सेटिंग्स में कॉलम “{column}” एक से अधिक बार सूचीबद्ध है"
    ),
    "The columnstore cannot be turned off while chunks are compressed; decompress them first": (
        "चंक कम्प्रेस होने पर कॉलमस्टोर बंद नहीं किया जा सकता; पहले उन्हें डीकम्प्रेस करें"
    ),
    "TimescaleDB {version} cannot return a setting to its own choice; name the columns instead": (
        "TimescaleDB {version} किसी सेटिंग को उसकी अपनी पसंद पर वापस नहीं ला सकता; इसके बजाय कॉलमों के नाम दें"
    ),
    "Merging compressed chunks is set in time, which an integer column does not count in": (
        "कम्प्रेस चंक मिलाना समय में सेट होता है, जिसे पूर्णांक कॉलम में नहीं गिना जाता"
    ),
    "A merge interval is counted in the units of the chunk interval": (
        "मिलान अंतराल चंक अंतराल की इकाइयों में गिना जाता है"
    ),
    "The merge interval must be a whole multiple of the chunk interval, larger than it": (
        "मिलान अंतराल चंक अंतराल का पूर्ण गुणक होना चाहिए, उससे बड़ा"
    ),
    "There is no retention policy to keep": "रखने के लिए कोई रिटेंशन नीति नहीं है",
    "There is no compression policy to keep": "रखने के लिए कोई कम्प्रेशन नीति नहीं है",
    "The retention policy of an integer column is a number of its values": (
        "पूर्णांक कॉलम की रिटेंशन नीति उसके मानों की संख्या है"
    ),
    "The compression policy of an integer column is a number of its values": (
        "पूर्णांक कॉलम की कम्प्रेशन नीति उसके मानों की संख्या है"
    ),
    "The retention policy of a {type} column is at most {count}": "{type} कॉलम की रिटेंशन नीति अधिकतम {count} है",
    "The compression policy of a {type} column is at most {count}": "{type} कॉलम की कम्प्रेशन नीति अधिकतम {count} है",
    "The retention policy of a {type} column cannot count in plain numbers": (
        "{type} कॉलम की रिटेंशन नीति साधारण संख्याओं में नहीं गिनी जा सकती"
    ),
    "The compression policy of a {type} column cannot count in plain numbers": (
        "{type} कॉलम की कम्प्रेशन नीति साधारण संख्याओं में नहीं गिनी जा सकती"
    ),
    "The retention policy of a {type} column cannot count in seconds": (
        "{type} कॉलम की रिटेंशन नीति सेकंड में नहीं गिनी जा सकती"
    ),
    "The compression policy of a {type} column cannot count in seconds": (
        "{type} कॉलम की कम्प्रेशन नीति सेकंड में नहीं गिनी जा सकती"
    ),
    "The retention policy of a {type} column cannot count in minutes": (
        "{type} कॉलम की रिटेंशन नीति मिनट में नहीं गिनी जा सकती"
    ),
    "The compression policy of a {type} column cannot count in minutes": (
        "{type} कॉलम की कम्प्रेशन नीति मिनट में नहीं गिनी जा सकती"
    ),
    "The retention policy of a {type} column cannot count in hours": (
        "{type} कॉलम की रिटेंशन नीति घंटे में नहीं गिनी जा सकती"
    ),
    "The compression policy of a {type} column cannot count in hours": (
        "{type} कॉलम की कम्प्रेशन नीति घंटे में नहीं गिनी जा सकती"
    ),
    "The existing reorder policy is paused; remove it before setting a new one": (
        "मौजूदा पुनःक्रमण नीति रुकी हुई है; नई सेट करने से पहले इसे हटाएँ"
    ),
    "Only a hypertable partitioned by an integer column takes an integer_now function": (
        "केवल पूर्णांक कॉलम से विभाजित हाइपरटेबल ही integer_now फ़ंक्शन लेता है"
    ),
    "TimescaleDB cannot take an integer_now function away; keep it or choose another": (
        "TimescaleDB integer_now फ़ंक्शन नहीं हटा सकता; इसे रखें या दूसरा चुनें"
    ),
    "There is no integer_now function to keep": "रखने के लिए कोई integer_now फ़ंक्शन नहीं है",
    "{function} is not a function TimescaleDB accepts as integer_now of a {type} column": (
        "{function} ऐसा फ़ंक्शन नहीं है जिसे TimescaleDB {type} कॉलम के integer_now के रूप में स्वीकार करता है"
    ),
    "A {type} column cannot hold the seconds since 1970": "{type} कॉलम 1970 से सेकंड नहीं रख सकता",
    "A {type} column cannot hold the milliseconds since 1970": (
        "{type} कॉलम 1970 से मिलीसेकंड नहीं रख सकता"
    ),
    "A {type} column cannot hold the microseconds since 1970": (
        "{type} कॉलम 1970 से माइक्रोसेकंड नहीं रख सकता"
    ),
    "TimescaleDB {version} has no compaction policy; it arrived in 2.29": (
        "TimescaleDB {version} में कम्पैक्शन नीति नहीं है; यह 2.29 में आई"
    ),
    "A compaction policy merges compressed chunks; turn the columnstore on": (
        "कम्पैक्शन नीति कम्प्रेस चंक मिलाती है; कॉलमस्टोर चालू करें"
    ),
    "Remove the columnstore policy to turn the columnstore off": (
        "कॉलमस्टोर बंद करने के लिए कॉलमस्टोर नीति हटाएँ"
    ),
    "Remove the compaction policy to turn the columnstore off": (
        "कॉलमस्टोर बंद करने के लिए कम्पैक्शन नीति हटाएँ"
    ),
    "An age policy on an integer column needs an integer_now function to tell the current value": (
        "पूर्णांक कॉलम पर आयु नीति को वर्तमान मान बताने के लिए integer_now फ़ंक्शन चाहिए"
    ),
    "Choose the time column the table is partitioned by": "वह समय कॉलम चुनें जिससे टेबल विभाजित है",
    "Choose the chunk interval": "चंक अंतराल चुनें",
    "TimescaleDB cannot change the time column of a hypertable": "TimescaleDB हाइपरटेबल का समय कॉलम नहीं बदल सकता",
    "Planning the hypertable change timed out": "हाइपरटेबल परिवर्तन की योजना बनाने का समय समाप्त हो गया",
    # हाइपरटेबल सेटिंग्स: पूर्वावलोकन।
    "TimescaleDB's choice for each chunk": "प्रत्येक चंक के लिए TimescaleDB की पसंद",
    "TimescaleDB's choice": "TimescaleDB की पसंद",
    "none": "कोई नहीं",
    "segment by {columns}": "{columns} से सेगमेंट करें",
    "order by {columns}": "{columns} से क्रमित करें",
    "sparse indexes {indexes}": "स्पॉर्स इंडेक्स {indexes}",
    "{kind} on {column}": "{column} पर {kind}",
    "no merging of chunks": "चंक मिलाना नहीं",
    "merge chunks into {length} as they are compressed": "कम्प्रेस होते समय चंक को {length} में मिलाएँ",
    "Turn the columnstore on: {changes}": "कॉलमस्टोर चालू करें: {changes}",
    "Columnstore settings for chunks compressed from now on: {changes}": (
        "अब से कम्प्रेस होने वाले चंक के लिए कॉलमस्टोर सेटिंग्स: {changes}"
    ),
    "Convert the table into a hypertable by {column} ({type}), chunks of {length}, and move its rows into chunks": (
        "{column} ({type}) के अनुसार टेबल को हाइपरटेबल में बदलें, चंक आकार {length}, और उसकी पंक्तियाँ चंक में ले जाएँ"
    ),
    "Convert the table into a hypertable by {column} ({type}), chunks of {length}, while it is empty": (
        "टेबल खाली रहते हुए उसे {column} ({type}) के अनुसार हाइपरटेबल में बदलें, चंक आकार {length}"
    ),
    "Remove the retention policy (job {job})": "रिटेंशन नीति हटाएँ (जॉब {job})",
    "Remove the columnstore policy (job {job})": "कॉलमस्टोर नीति हटाएँ (जॉब {job})",
    "Remove the reorder policy (job {job})": "पुनःक्रमण नीति हटाएँ (जॉब {job})",
    "Remove the compaction policy (job {job})": "कम्पैक्शन नीति हटाएँ (जॉब {job})",
    "Add a retention policy: drop chunks older than {length}": (
        "रिटेंशन नीति जोड़ें: {length} से पुराने चंक हटाएँ"
    ),
    "Add a columnstore policy: compress chunks older than {length}": (
        "कॉलमस्टोर नीति जोड़ें: {length} से पुराने चंक कम्प्रेस करें"
    ),
    "Add a compaction policy: merge small compressed chunks on TimescaleDB's schedule": (
        "कम्पैक्शन नीति जोड़ें: TimescaleDB के शेड्यूल पर छोटे कम्प्रेस चंक मिलाएँ"
    ),
    "Add a reorder policy by index {index}": "इंडेक्स {index} से पुनःक्रमण नीति जोड़ें",
    "New chunks cover {length}; existing chunks keep their range": (
        "नए चंक {length} कवर करते हैं; मौजूदा चंक अपनी सीमा रखते हैं"
    ),
    "Hash {column} into {partitions} partitions for new chunks": (
        "नए चंक के लिए {column} को {partitions} विभाजनों में हैश करें"
    ),
    "Add a hash dimension on {column} with {partitions} partitions": (
        "{column} पर {partitions} विभाजनों वाला हैश आयाम जोड़ें"
    ),
    "Turn the columnstore off": "कॉलमस्टोर बंद करें",
    "Place new chunks in tablespace {tablespace} too": "नए चंक को टेबलस्पेस {tablespace} में भी रखें",
    "Stop placing new chunks in tablespace {tablespace}": (
        "नए चंक को टेबलस्पेस {tablespace} में रखना बंद करें"
    ),
    "Create function {function} returning the seconds since 1970 as {type}": (
        "फ़ंक्शन {function} बनाएँ जो 1970 से सेकंड {type} के रूप में लौटाए"
    ),
    "Create function {function} returning the milliseconds since 1970 as {type}": (
        "फ़ंक्शन {function} बनाएँ जो 1970 से मिलीसेकंड {type} के रूप में लौटाए"
    ),
    "Create function {function} returning the microseconds since 1970 as {type}": (
        "फ़ंक्शन {function} बनाएँ जो 1970 से माइक्रोसेकंड {type} के रूप में लौटाए"
    ),
    "Policies take the current value of the time column from {function}": (
        "नीतियाँ समय कॉलम का वर्तमान मान {function} से लेती हैं"
    ),
    "Moves about {count} rows into chunks as a job in Activity; the table is locked against reads and writes until it ends": (
        "“गतिविधि” में जॉब के रूप में लगभग {count} पंक्तियाँ चंक में ले जाता है; समाप्त होने तक टेबल पढ़ने और लिखने के लिए लॉक रहती है"
    ),
    "Moves an unknown number of rows into chunks as a job in Activity; the table is locked against reads and writes until it ends": (
        "“गतिविधि” में जॉब के रूप में अज्ञात संख्या की पंक्तियाँ चंक में ले जाता है; समाप्त होने तक टेबल पढ़ने और लिखने के लिए लॉक रहती है"
    ),
    "Rolled back whole if it fails, is cancelled or runs past {seconds} seconds; nothing is left half converted": (
        "विफल होने, रद्द होने या {seconds} सेकंड से अधिक चलने पर पूरा वापस लौटा दिया जाता है; आधा बदला हुआ कुछ नहीं बचता"
    ),
    "DataPlayer cannot turn a hypertable back into an ordinary table": (
        "DataPlayer हाइपरटेबल को वापस सामान्य टेबल में नहीं बदल सकता"
    ),
    "TimescaleDB keeps dropping whole chunks past the retention age on its own schedule, after this session ends": (
        "इस सत्र के समाप्त होने के बाद TimescaleDB अपने शेड्यूल पर रिटेंशन आयु से पुराने पूरे चंक हटाता रहेगा"
    ),
    "{target} already matches these settings": "{target} पहले से इन सेटिंग्स से मेल खाता है",
    "Change {target}": "{target} बदलें",
    "Review the hypertable plan before applying it": "लागू करने से पहले हाइपरटेबल योजना देखें",
    "Moving rows into chunks runs as a job; start it from the plan": (
        "पंक्तियाँ चंक में ले जाना जॉब के रूप में चलता है; इसे योजना से शुरू करें"
    ),
    "Converted to a hypertable": "हाइपरटेबल में बदल दिया गया",
    "Hypertable changed: 1 change applied": "हाइपरटेबल बदला: 1 परिवर्तन लागू हुआ",
    "Hypertable changed: {count} changes applied": "हाइपरटेबल बदला: {count} परिवर्तन लागू हुए",
    "This change is applied at once rather than as a job": "यह परिवर्तन जॉब के रूप में नहीं, बल्कि तुरंत लागू होता है",
    "The table could not be found; nothing was converted": "टेबल नहीं मिली; कुछ भी नहीं बदला गया",
    "The table was renamed after review; nothing was converted": (
        "देखने के बाद टेबल का नाम बदल गया; कुछ भी नहीं बदला गया"
    ),
    # हाइपरटेबल के रूप में डिज़ाइन की गई टेबलें।
    "Hypertable": "हाइपरटेबल",
    "Columnstore": "कॉलमस्टोर",
    "Retention policy": "रिटेंशन नीति",
    "Columnstore policy": "कॉलमस्टोर नीति",
    "Compaction policy": "कम्पैक्शन नीति",
    "Reorder policy": "पुनःक्रमण नीति",
    "Integer now": "Integer now",
    "Function {name}": "फ़ंक्शन {name}",
    "Hash dimension {column}": "हैश आयाम {column}",
    "The segment list names a column that is not there": "सेगमेंट सूची ऐसे कॉलम का नाम देती है जो वहाँ नहीं है",
    "The order list names a column that is not there": "क्रम सूची ऐसे कॉलम का नाम देती है जो वहाँ नहीं है",
    "The sparse index names a column that is not there": "स्पॉर्स इंडेक्स ऐसे कॉलम का नाम देता है जो वहाँ नहीं है",
    "The time dimension names a column that is not there": "समय आयाम ऐसे कॉलम का नाम देता है जो वहाँ नहीं है",
    "The hash dimension names a column that is not there": "हैश आयाम ऐसे कॉलम का नाम देता है जो वहाँ नहीं है",
    "Choose the columns to segment by": "सेगमेंट के लिए कॉलम चुनें",
    "Choose the columns to order by": "क्रम के लिए कॉलम चुनें",
    "Choose the columns of the sparse indexes": "स्पॉर्स इंडेक्स के कॉलम चुनें",
    "The reorder policy names an index that is not there": "पुनःक्रमण नीति ऐसे इंडेक्स का नाम देती है जो वहाँ नहीं है",
    "The TimescaleDB API is split across schemas": "TimescaleDB API कई स्कीमाओं में विभाजित है",
    "This setting cannot be made while the table is created": "टेबल बनाते समय यह सेटिंग नहीं की जा सकती",
    "\"{column}\" cannot partition a hypertable; choose a timestamp or date column": (
        "“{column}” हाइपरटेबल को विभाजित नहीं कर सकता; timestamp या date कॉलम चुनें"
    ),
    "\"{column}\" partitions the hypertable, so it must have a value": (
        "“{column}” हाइपरटेबल को विभाजित करता है, इसलिए उसका मान होना चाहिए"
    ),
    "TimescaleDB {version} partitions by UUIDv7 only partly; choose a timestamp column": (
        "TimescaleDB {version} UUIDv7 से केवल आंशिक रूप से विभाजित करता है; timestamp कॉलम चुनें"
    ),
}
