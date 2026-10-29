/** مراجع رسمها شخص بين عمودين (features/declared). */
import type { Messages } from "../en"

export const declared: Messages["declared"] = {
  title: "المراجع المعلنة",
  declare_one: "إعلان مرجع",
  read_failed: "تعذّرت قراءة المراجع المرسومة من هذه العقدة",
  none: "لا شيء",
  remove_tooltip: "إزالة هذا المرجع",
  remove: {
    title: "إزالة هذا المرجع؟",
    message: "{from} → {to} يتوقف عرضه هنا وفي الطرف الآخر. لا يتغير أي من المصدرين.",
    confirm: "إزالة",
    done: "تمت إزالة المرجع المعلن",
    failed: "تعذّرت إزالة هذا المرجع",
  },
  dialog: {
    subtitle: "من عمود في {node} إلى عمود في أي مكان آخر",
    near: "هذا العمود",
    points_at: "يشير إلى",
    far: "ذلك العمود",
    declare: "إعلان",
    read_failed: "تعذّرت قراءة هذه العقدة كصفوف",
    failed: "تعذّر إعلان هذا المرجع",
  },
}
