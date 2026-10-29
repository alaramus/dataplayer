/** نماذج تُرسم من مخطط JSON (shared/SchemaForm). */
import type { Messages } from "../en"

export const schema_form: Messages["schema_form"] = {
  hidden: "<مخفي>",
  show_password: "إظهار كلمة المرور",
  hide_password: "إخفاء كلمة المرور",
  choose: "اختيار {label}",
  is_number: "{label}: رقم",
  at_least: "{label}: {n} على الأقل",
  at_most: "{label}: {n} على الأكثر",
  required: "{label}: مطلوب",
  min_length:
    "{label}: لا يلزم أي حرف | {label}: حرف واحد على الأقل | {label}: حرفان على الأقل | {label}: {n} أحرف على الأقل | {label}: {n} حرفًا على الأقل | {label}: {n} حرف على الأقل",
}
