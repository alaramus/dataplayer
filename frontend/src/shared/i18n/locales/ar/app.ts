/** كلمات لا تخص شاشة بعينها: تسجيل الدخول، واللغة، والسمات. */
import type { Messages } from "../en"

export const common: Messages["common"] = {
  back_to_workspace: "العودة إلى مساحة العمل",
}

export const language: Messages["language"] = {
  label: "اللغة",
  browser: "لغة المتصفح",
  browser_hint: "اللغة التي يطلبها هذا المتصفح، أو الإنجليزية",
}

export const auth: Messages["auth"] = {
  sign_in: "تسجيل الدخول",
  email: "البريد الإلكتروني",
  password: "كلمة المرور",
  email_required: "البريد الإلكتروني مطلوب",
  password_required: "كلمة المرور مطلوبة",
  checking_server: "جارٍ التحقق من الخادم…",
  retry_connection: "إعادة محاولة الاتصال",
  sign_in_failed: "تعذّر تسجيل الدخول. تحقق من البريد الإلكتروني وكلمة المرور.",
  welcome_tagline: "مكان واحد لكل مصدر بيانات تعمل معه",
}

export const theme: Messages["theme"] = {
  label: "السمة",
  light: "فاتحة",
  paper_light: "ورق فاتح",
  paper_light_hint: "ورق فاتح دافئ بلمسة برونزية",
  dark: "داكنة",
  paper: "ورق داكن",
  paper_hint: "ورق داكن دافئ بلمسة برونزية",
  midnight: "منتصف الليل",
  midnight_hint: "الأكثر عتمة: كحلي شبه أسود بلمسة أزرق جليدي",
  dark_blue: "أزرق داكن",
  dark_blue_hint: "كحلي مشبع بلمسة سماوية",
  dark_purple: "بنفسجي داكن",
  dark_purple_hint: "نيون بنفسجي بلمسات وردية وسماوية",
  system: "النظام",
  system_hint: "فاتحة أو داكنة، حسب إعداد نظام التشغيل",
  switch_to: "التبديل إلى {theme}",
}
