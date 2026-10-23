/** सर्वर का लॉग (features/logs)। */
import type { Messages } from "../en"

export const logs: Messages["logs"] = {
  logs: "लॉग",
  tooltip: "सर्वर का लॉग",
  levels: {
    all: "सब कुछ",
    warning: "चेतावनियाँ और त्रुटियाँ",
    error: "त्रुटियाँ",
  },
  processes: {
    all: "हर प्रक्रिया",
    backend: "बैकएंड",
    metrics: "मीट्रिक",
    search_keeper: "खोज अनुक्रमणिका",
  },
  only_superuser: "सर्वर का लॉग केवल सुपरयूज़र पढ़ सकता है।",
  search: "पाठ, ref या पथ खोजें",
  follow: "अनुसरण करें",
  reload: "लॉग फिर से पढ़ें",
  read_failed: "लॉग पढ़ा नहीं जा सका",
  not_kept: "यह सर्वर कोई लॉग फ़ाइल नहीं रखता। उन्हें रखने के लिए LOG_DIR सेट करें; तब तक लॉग सर्वर के मानक आउटपुट पर है।",
  nothing: "लॉग में कुछ भी मेल नहीं खाता।",
  ref: "ref {ref}",
  copy: "यह प्रविष्टि कॉपी करें",
  copied: "कॉपी किया गया",
  copy_refused: "ब्राउज़र ने कॉपी करने की अनुमति नहीं दी",
  older: "पुरानी प्रविष्टियाँ",
}
