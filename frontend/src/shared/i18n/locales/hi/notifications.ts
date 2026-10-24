/** सूचनाएँ और स्क्रीन पर चल रहा काम (shared/notifications, shared/operations)। */
import type { Messages } from "../en"

export const notifications: Messages["notifications"] = {
  toasts: {
    more: "गतिविधि में {n} और",
    dismiss: "खारिज करें",
  },
  operations: {
    starting: "शुरू हो रहा है",
    waiting_to_resume: "फिर से शुरू होने की प्रतीक्षा",
    upload_sent: "अपलोड भेजा गया; सर्वर की प्रतीक्षा है",
  },
}
