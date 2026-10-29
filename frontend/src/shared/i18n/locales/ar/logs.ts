/** سجل الخادم (features/logs). */
import type { Messages } from "../en"

export const logs: Messages["logs"] = {
  logs: "السجلات",
  tooltip: "سجل الخادم",
  levels: {
    all: "كل شيء",
    warning: "التحذيرات والأخطاء",
    error: "الأخطاء",
  },
  processes: {
    all: "كل العمليات",
    backend: "الخادم الخلفي",
    metrics: "المقاييس",
    search_keeper: "فهرس البحث",
  },
  only_superuser: "لا يقرأ سجل الخادم إلا مستخدم فائق.",
  search: "البحث في النص أو مرجع أو مسار",
  follow: "متابعة",
  reload: "إعادة قراءة السجل",
  read_failed: "تعذّرت قراءة السجل",
  not_kept: "لا يحتفظ هذا الخادم بملفات سجلات. اضبط LOG_DIR للاحتفاظ بها؛ وإلى أن يتم ذلك، يكون السجل على المخرجات القياسية للخادم.",
  nothing: "لا شيء في السجل يطابق.",
  ref: "المرجع {ref}",
  copy: "نسخ هذا المدخل",
  copied: "تم النسخ",
  copy_refused: "لم يسمح المتصفح بالنسخ",
  older: "مدخلات أقدم",
}
