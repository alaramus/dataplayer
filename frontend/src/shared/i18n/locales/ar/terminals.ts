/** الطرفيات (features/terminals). */
import type { Messages } from "../en"

export const terminals: Messages["terminals"] = {
  terminals: "الطرفيات",
  press: {
    hide: "إخفاء الطرفيات",
    open: "فتح طرفية",
    open_on: "فتح طرفية على {name}",
    on: "طرفية على {name}",
    with_open: "{doing} · {n} مفتوحة",
  },
  connection: "الاتصال",
  numbered: "{name} ({n})",
  notice: {
    connecting: "جارٍ الاتصال…",
    ended: "انتهت الصدفة",
    ended_with: "انتهت الصدفة بالحالة {status}",
    lost: "انقطع الاتصال بالخادم",
    sign_in: "سجّل الدخول مجددًا لفتح طرفية",
  },
  close: "إغلاق هذه الطرفية",
  open: "فتح طرفية",
  none_menu: "لا يوجد اتصال لديك له طرفية",
  none_menu_hint: "اتصال SSH لديه طرفية",
  none: "لا يوجد أي اتصال لديك له طرفية. اتصال SSH لديه طرفية.",
  choose: "لا توجد طرفية مفتوحة. اختر الاتصال الذي تريد فتح طرفية عليه:",
  open_again: "فتح مجددًا",
  unlock: "فتح قفل المفتاح",
}
