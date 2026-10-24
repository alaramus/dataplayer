/** एक पंक्ति, ऊपर से नीचे पढ़ी गई (features/record)। */
import type { Messages } from "../en"

export const record: Messages["record"] = {
  columns: {
    keys: "कुंजी",
    name: "कॉलम",
    type: "प्रकार",
    value: "मान",
  },
  copied: "{name} कॉपी किया गया",
  read_failed: "यह पंक्ति पढ़ी नहीं जा सकी",
  no_row: "यहाँ कोई पंक्ति नहीं",
  no_columns: "कोई कॉलम नहीं",
  copy_value: "यह मान कॉपी करें",
  navigation: "पंक्ति नेविगेशन",
  previous: "पिछली पंक्ति",
  next: "अगली पंक्ति",
}
