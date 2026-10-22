/** दो कॉलमों के बीच किसी के द्वारा खींचे गए संदर्भ (features/declared)। */
import type { Messages } from "../en"

export const declared: Messages["declared"] = {
  title: "घोषित संदर्भ",
  declare_one: "एक संदर्भ घोषित करें",
  read_failed: "इस नोड से खींचे गए संदर्भ पढ़े नहीं जा सके",
  none: "कोई नहीं",
  remove_tooltip: "यह संदर्भ हटाएँ",
  remove: {
    title: "यह संदर्भ हटाएँ?",
    message: "{from} → {to} अब यहाँ और दूसरे सिरे पर प्रस्तावित नहीं होगा। कोई भी स्रोत बदला नहीं जाता।",
    confirm: "हटाएँ",
    done: "घोषित संदर्भ हटाया गया",
    failed: "यह संदर्भ हटाया नहीं जा सका",
  },
  dialog: {
    subtitle: "{node} के एक कॉलम से कहीं और के एक कॉलम तक",
    near: "यह कॉलम",
    points_at: "इंगित करता है",
    far: "वह कॉलम",
    declare: "घोषित करें",
    read_failed: "यह नोड पंक्तियों के रूप में पढ़ा नहीं जा सका",
    failed: "यह संदर्भ घोषित नहीं किया जा सका",
  },
}
