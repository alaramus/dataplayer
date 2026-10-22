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
}
