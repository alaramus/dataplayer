/** هيكل التطبيق: App والموجّه والمخازن والجلسات والخوادم والمقابس والتنزيلات والحافظة. */
import type { Messages } from "../en"

export const shell: Messages["shell"] = {
  leave_work: {
    title: "مغادرة العمل الجاري في المتصفح؟",
    message:
      "ستتوقف عمليات الرفع وغيرها من العمل الجاري في تبويب المتصفح هذا عند التبديل. أما المهام التي يملكها الخادم بالفعل فستستمر هناك.",
    confirm: "تبديل الخادم",
  },
  default_server: "الخادم الافتراضي",
  server_url: {
    full_http: "أدخل عنوان URL كاملًا لخادم HTTP أو HTTPS.",
    full_url: "أدخل عنوان URL كاملًا، مثل https://data.example.com.",
    http_only: "استخدم عنوان URL لخادم HTTP أو HTTPS.",
    no_extras: "يجب ألا يحتوي عنوان URL للخادم على بيانات اعتماد أو استعلام أو جزء.",
    invalid_destination: "وجهة غير صالحة",
  },
  servers: {
    invalid_profile: "أدخل اسم خادم وعنوان URL صالحين لـ HTTP(S).",
    default_is_configured: "الخادم الافتراضي مُهيأ من هذا التنصيب.",
    already_saved: "هذا الخادم محفوظ بالفعل.",
    too_many: "أزل خادمًا محفوظًا قبل إضافة آخر (الحد الأقصى {n}).",
  },
}
