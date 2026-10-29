/** صف واحد يُقرأ من الأعلى إلى الأسفل (features/record). */
import type { Messages } from "../en"

export const record: Messages["record"] = {
  columns: {
    keys: "المفتاح",
    name: "العمود",
    type: "النوع",
    value: "القيمة",
  },
  copied: "تم نسخ {name}",
  read_failed: "تعذّرت قراءة هذا الصف",
  no_row: "لا يوجد صف هنا",
  no_columns: "لا أعمدة",
  copy_value: "نسخ هذه القيمة",
  navigation: "التنقل بين الصفوف",
  previous: "السابق",
  next: "التالي",
}
