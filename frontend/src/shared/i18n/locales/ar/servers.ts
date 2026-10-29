/** أي خادم DataPlayer يتحدث إليه هذا التبويب (features/servers). */
import type { Messages } from "../en"

export const servers: Messages["servers"] = {
  check: {
    https_only: "تستخدم هذه الصفحة HTTPS. استخدم عنوان خادم HTTPS.",
    unreachable:
      "تعذّر الوصول إلى خادم DataPlayer متوافق. تحقق من العنوان وإصدار الخادم والشهادة وأصل الواجهة المسموح به (CORS).",
    incompatible: "هذا الخادم غير متوافق مع هذا الإصدار من DataPlayer.",
  },
  name_invalid: "أدخل اسم خادم من 1 إلى 100 حرف.",
  name: "اسم الخادم",
  url: "عنوان URL للخادم",
  url_example: "https://data.example.com",
  boundary: {
    title: "الاتصال بـ DataPlayer",
  },
  link: {
    new_server: "خادم جديد",
    connect_failed: "تعذّر الاتصال بهذا الخادم.",
    title: "اختيار الخادم لهذا الرابط",
    notice: "يستخدم هذا الرابط خادمًا آخر. تحقق من العنوان قبل الاتصال؛ قد تحتاج إلى تسجيل الدخول هناك.",
    connect: "التحقق والاتصال",
  },
  switcher: {
    save_failed: "تعذّر حفظ الخادم في هذا المتصفح.",
    compatible: "خادم DataPlayer متوافق.",
    saved: "تم حفظ الخادم. اختر «الاتصال» لاستخدامه في هذا التبويب.",
    choose: "اختيار خادم",
    servers: "الخوادم",
    intro: "اختر الخادم لهذا التبويب في المتصفح. الحسابات منفصلة في كل خادم.",
    current: "الحالي: {name} · {url}",
    current_mark: " · الحالي",
    check: "فحص",
    connect: "الاتصال",
    edit: "تحرير الخادم",
    remove: "إزالة الخادم",
    add: "إضافة خادم",
    check_connection: "فحص الاتصال",
    save_and_connect: "الحفظ والاتصال",
    save: "حفظ الخادم",
  },
}
