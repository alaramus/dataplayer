/** جولة الترحيب (features/onboarding)، والكلمات القليلة لنافذة
    الدليل (features/guide) والقراءة بصوت عالٍ (features/speech). */
import type { Messages } from "../en"

export const onboarding: Messages["onboarding"] = {
  title: "مرحبًا بك في DataPlayer",
  intro: "اختر لغة وشكل التطبيق، ثم خذ جولة قصيرة فيما يمكنه فعله، مقطع صامت واحد لكل جزء رئيسي من أجزائه.",
  steps: {
    new_connection: "إنشاء اتصال جديد",
    tabs: "العمل مع التبويبات",
    table: "العمل مع الجداول",
    pipelines: "العمل مع خطوط الأنابيب",
    dashboards: "العمل مع لوحات المعلومات",
    ai_agent: "العمل مع وكيل الذكاء الاصطناعي",
  },
  position: "الخطوة {n} من {total}",
  start: "بدء الجولة",
  finish: "إنهاء",
  next: "التالي",
  skip_tour: "تخطي الجولة",
  skip: "تخطي",
  mark_failed: "تعذّر تعليم الجولة كمشاهدة",
  close_title: "إغلاق جولة الترحيب؟",
  close_message: "لن تُفتح الجولة من تلقاء نفسها مرة أخرى. يمكنك إعادتها في أي وقت من التفضيلات، ضمن جولة الترحيب.",
  close_confirm: "إغلاق الجولة",
  keep_watching: "متابعة المشاهدة",
  guide: {
    title: "الدليل",
    not_a_page: "هذا الرابط لا يؤدي إلى صفحة في الدليل",
    read_failed: "تعذّرت قراءة هذه الصفحة من الدليل",
  },
  speech: {
    listen: "استماع",
    stop: "إيقاف القراءة بصوت عالٍ",
    browser_default: "افتراضي المتصفح",
  },
}
