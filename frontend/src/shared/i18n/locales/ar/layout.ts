/** محرك اللوحات أسفل مساحة العمل (shared/workspace). */
import type { Messages } from "../en"

export const layout: Messages["layout"] = {
  leaf: {
    open_tabs: "التبويبات المفتوحة",
    close: "إغلاق {title}",
    close_others: "إغلاق التبويبات الأخرى",
    show: "إظهار {title}",
    show_this_section: "إظهار هذا القسم",
    hide: "إخفاء",
    put_aside: "إبعاد {title}",
    put_this_section_aside: "إبعاد هذا القسم",
  },
  taskbar: {
    label: "الأقسام المبعدة",
    bring_back: "إرجاع {title}",
  },
  return_to_panel: "العودة إلى اللوحة",
}
