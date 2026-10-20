/** Le moteur de panneaux sous l'espace de travail (shared/workspace). */
import type { Messages } from "../en"

export const layout: Messages["layout"] = {
  leaf: {
    open_tabs: "Onglets ouverts",
    close: "Fermer « {title} »",
    close_others: "Fermer les autres onglets",
    show: "Afficher « {title} »",
    show_this_section: "Afficher cette section",
    hide: "Masquer",
    put_aside: "Mettre « {title} » de côté",
    put_this_section_aside: "Mettre cette section de côté",
  },
  taskbar: {
    label: "Sections mises de côté",
    bring_back: "Ramener « {title} »",
  },
  return_to_panel: "Retour au panneau",
}
