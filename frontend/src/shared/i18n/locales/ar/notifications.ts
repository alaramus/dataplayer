/** الإشعارات والعمل الجاري على الشاشة (shared/notifications, shared/operations). */
import type { Messages } from "../en"

export const notifications: Messages["notifications"] = {
  toasts: {
    more: "{n} أخرى في النشاط",
    dismiss: "تجاهل",
  },
  operations: {
    starting: "بدء التشغيل",
    waiting_to_resume: "انتظار الاستئناف",
    upload_sent: "تم إرسال الرفع؛ انتظار الخادم",
  },
}
