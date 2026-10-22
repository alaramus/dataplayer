/** पंक्तियों के पृष्ठ के चार्ट (features/charts)। */
import type { Messages } from "../en"

export const charts: Messages["charts"] = {
  read_failed: "चार्ट पृष्ठ पढ़ा नहीं जा सका",
  page: {
    none: "वर्तमान पृष्ठ · पंक्तियाँ 0",
    range: "वर्तमान पृष्ठ · पंक्तियाँ {first}–{last}",
    more: "बाद की पंक्तियाँ शामिल नहीं हैं।",
    bounded: "चार्ट केवल इस सीमित परिणाम का उपयोग करता है।",
  },
  no_data: "इस पृष्ठ पर आलेखन योग्य कोई मान नहीं",
  no_measure: "इस पृष्ठ पर चार्ट बनाने के लिए कोई दृश्य संख्यात्मक कॉलम नहीं",
  types: {
    line: "रेखा",
    bar: "बार",
    pie: "पाई",
  },
  row: "पंक्ति",
  other: "अन्य",
  numeric_on_page: "{name} (इस पृष्ठ पर संख्यात्मक)",
  fields: {
    suggestion: "सुझाया गया व्यू",
    type: "चार्ट प्रकार",
    label: "लेबल",
    value: "मान",
    x: "X अक्ष",
    y: "Y अक्ष",
  },
  best_fit: "सर्वोत्तम उपयुक्त",
  suggestions: {
    over: "{dimension} पर {measure}",
    by: "{dimension} के अनुसार {measure}",
    share: "{dimension} के अनुसार {measure} का हिस्सा",
  },
}
