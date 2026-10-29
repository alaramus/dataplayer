/** رسوم بيانية لصفحة صفوف (features/charts). */
import type { Messages } from "../en"

export const charts: Messages["charts"] = {
  read_failed: "تعذّرت قراءة صفحة الرسم البياني",
  page: {
    none: "الصفحة الحالية · الصفوف 0",
    range: "الصفحة الحالية · الصفوف {first}-{last}",
    more: "لا تشمل الصفوف اللاحقة.",
    bounded: "يستخدم الرسم البياني هذه النتيجة المحدودة فقط.",
  },
  no_data: "لا توجد قيم قابلة للرسم في هذه الصفحة",
  no_measure: "لا تحتوي هذه الصفحة على عمود رقمي ظاهر لرسمه",
  types: {
    line: "خط",
    bar: "أعمدة",
    pie: "دائري",
  },
  row: "صف",
  other: "أخرى",
  numeric_on_page: "{name} (رقمي في هذه الصفحة)",
  fields: {
    suggestion: "العرض المقترح",
    type: "نوع الرسم البياني",
    label: "التسمية",
    value: "القيمة",
    x: "المحور X",
    y: "المحور Y",
  },
  best_fit: "أفضل ملاءمة",
  suggestions: {
    over: "{measure} عبر {dimension}",
    by: "{measure} حسب {dimension}",
    share: "نسبة {measure} حسب {dimension}",
  },
}
