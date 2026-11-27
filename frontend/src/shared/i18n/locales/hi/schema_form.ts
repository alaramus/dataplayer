/** JSON स्कीमा से बने फ़ॉर्म (shared/SchemaForm)। */
import type { Messages } from "../en"

export const schema_form: Messages["schema_form"] = {
  hidden: "<छिपा हुआ>",
  show_password: "पासवर्ड दिखाएँ",
  hide_password: "पासवर्ड छिपाएँ",
  choose: "{label} चुनें",
  is_number: "{label} एक संख्या है",
  at_least: "{label} कम से कम {n} है",
  at_most: "{label} अधिक से अधिक {n} है",
  required: "{label} आवश्यक है",
  min_length: "{label} में कम से कम {n} वर्ण होना चाहिए | {label} में कम से कम {n} वर्ण होने चाहिए",
  from_file: "{label} फ़ाइल से पढ़ें",
  file_too_large: "{label}: यह फ़ाइल किसी प्रमाणपत्र या कुंजी से बहुत बड़ी है; वही फ़ाइल चुनें",
  file_not_text: "{label}: यह फ़ाइल टेक्स्ट नहीं है। PEM या JSON फ़ाइल चुनें, बाइनरी नहीं",
  file_too_long: "{label}: फ़ाइल में {n} से अधिक वर्ण हैं, जितने यह फ़ील्ड लेता है उससे ज़्यादा",
}
