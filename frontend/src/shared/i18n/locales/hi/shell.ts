/** एप्लिकेशन शेल: App, राउटर, स्टोर, सत्र, सर्वर, सॉकेट, डाउनलोड, क्लिपबोर्ड। */
import type { Messages } from "../en"

export const shell: Messages["shell"] = {
  leave_work: {
    title: "चालू ब्राउज़र काम छोड़ें?",
    message:
      "स्विच करने पर इस ब्राउज़र टैब में चल रहे अपलोड और अन्य काम रुक जाएँगे। सर्वर के स्वामित्व वाले जॉब वहाँ चलते रहेंगे।",
    confirm: "सर्वर बदलें",
  },
  default_server: "डिफ़ॉल्ट सर्वर",
  server_url: {
    full_http: "पूरा HTTP या HTTPS सर्वर URL दर्ज करें।",
    full_url: "पूरा URL दर्ज करें, जैसे https://data.example.com।",
    http_only: "HTTP या HTTPS सर्वर URL का उपयोग करें।",
    no_extras: "सर्वर URL में क्रेडेंशियल, क्वेरी या फ़्रैगमेंट नहीं होना चाहिए।",
    invalid_destination: "अमान्य गंतव्य",
  },
  servers: {
    invalid_profile: "मान्य सर्वर नाम और HTTP(S) URL दर्ज करें।",
    default_is_configured: "डिफ़ॉल्ट सर्वर इस इंस्टॉलेशन द्वारा कॉन्फ़िगर किया गया है।",
    already_saved: "वह सर्वर पहले से सहेजा गया है।",
    too_many: "दूसरा जोड़ने से पहले एक सहेजा गया सर्वर हटाएँ (अधिकतम {n})।",
  },
}
