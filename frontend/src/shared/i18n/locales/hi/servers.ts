/** Which DataPlayer server this tab talks to (features/servers). */
import type { Messages } from "../en"

export const servers: Messages["servers"] = {
  check: {
    https_only: "यह पृष्ठ HTTPS का उपयोग करता है। HTTPS सर्वर पता दें।",
    unreachable:
      "किसी संगत DataPlayer सर्वर तक नहीं पहुँचा जा सका। पता, सर्वर संस्करण, प्रमाणपत्र और अनुमत फ़्रंटएंड मूल (CORS) जाँचें।",
    incompatible: "यह सर्वर DataPlayer के इस संस्करण के साथ संगत नहीं है।",
  },
  name_invalid: "1 से 100 अक्षरों का सर्वर नाम दर्ज करें।",
  name: "सर्वर नाम",
  url: "सर्वर URL",
  url_example: "https://data.example.com",
  boundary: {
    title: "DataPlayer से कनेक्ट करें",
  },
  link: {
    new_server: "नया सर्वर",
    connect_failed: "इस सर्वर से कनेक्ट नहीं हो सका।",
    title: "इस लिंक के लिए सर्वर चुनें",
    notice:
      "यह लिंक किसी अन्य सर्वर का उपयोग करता है। कनेक्ट करने से पहले पता जाँचें; वहाँ आपको साइन इन करना पड़ सकता है।",
    connect: "जाँचें और कनेक्ट करें",
  },
  switcher: {
    save_failed: "इस ब्राउज़र में सर्वर सहेजा नहीं जा सका।",
    compatible: "संगत DataPlayer सर्वर।",
    saved: "सर्वर सहेजा गया। इस टैब में उपयोग करने के लिए कनेक्ट चुनें।",
    choose: "सर्वर चुनें",
    servers: "सर्वर",
    intro: "इस ब्राउज़र टैब के लिए सर्वर चुनें। हर सर्वर पर खाते अलग होते हैं।",
    current: "वर्तमान: {name} · {url}",
    current_mark: " · वर्तमान",
    check: "जाँचें",
    connect: "कनेक्ट करें",
    edit: "सर्वर संपादित करें",
    remove: "सर्वर हटाएँ",
    add: "सर्वर जोड़ें",
    check_connection: "कनेक्शन जाँचें",
    save_and_connect: "सहेजें और कनेक्ट करें",
    save: "सर्वर सहेजें",
  },
}
