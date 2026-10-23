/** El motor de paneles bajo el espacio de trabajo (shared/workspace). */
import type { Messages } from "../en"

export const layout: Messages["layout"] = {
  leaf: {
    open_tabs: "Pestañas abiertas",
    close: "Cerrar {title}",
    close_others: "Cerrar las demás pestañas",
    show: "Mostrar {title}",
    show_this_section: "Mostrar esta sección",
    hide: "Ocultar",
    put_aside: "Apartar {title}",
    put_this_section_aside: "Apartar esta sección",
  },
  taskbar: {
    label: "Secciones apartadas",
    bring_back: "Recuperar {title}",
  },
  return_to_panel: "Volver al panel",
}
