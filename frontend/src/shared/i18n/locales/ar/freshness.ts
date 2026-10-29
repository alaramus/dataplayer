/** عمر البيانات ووتيرة تحديثها (shared/freshness). */
import type { Messages } from "../en"

export const freshness: Messages["freshness"] = {
  live: "مباشر",
  nothing: "لا شيء",
  read_now: "تمت القراءة من المصدر الآن.",
  read_ago: "تمت القراءة من المصدر منذ {age}.",
  keeps_as_source_says: "يحتفظ هذا الاتصال بالإجابات للمدة التي يحددها المصدر.",
  keeps_nothing: "لا يحتفظ هذا الاتصال بشيء: كل قراءة تصل إلى المصدر.",
  keeps_for: "يحتفظ هذا الاتصال بالإجابات لمدة {window}.",
}
