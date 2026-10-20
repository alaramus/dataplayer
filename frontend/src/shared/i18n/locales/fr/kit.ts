/** Les mots propres au kit de composants : états vides, boutons de copie, sélecteurs (shared/ui). */
import type { Messages } from "../en"

export const kit: Messages["kit"] = {
  copy: {
    tooltip: "Copier",
  },
  color_picker: {
    reset: "Réinitialiser la couleur",
  },
  file: {
    choose_one: "Choisir un fichier",
    choose_many: "Choisir des fichiers",
  },
  date_time: {
    pick: "Choisir un jour et une heure, en UTC",
  },
  fullscreen: {
    enter: "Remplir l'écran",
    leave: "Quitter le plein écran",
    unsupported: "Ce navigateur ne peut pas remplir l'écran",
  },
  layout: {
    user_menu: "Menu utilisateur",
    preferences: "Préférences",
    admin: "Administration",
    sign_out: "Se déconnecter",
  },
  option: {
    clear: "Effacer",
  },
  progress: {
    paused: "En pause",
  },
  table: {
    empty: "Rien à afficher",
  },
  tree: {
    tick: "Cocher « {name} »",
  },
}
