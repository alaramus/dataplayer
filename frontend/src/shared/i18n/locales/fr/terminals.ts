/** Shells (features/terminals). */
import type { Messages } from "../en"

export const terminals: Messages["terminals"] = {
  terminals: "Shells",
  press: {
    hide: "Masquer les shells",
    open: "Ouvrir un shell",
    open_on: "Ouvrir un shell sur {name}",
    on: "Shell sur {name}",
    with_open: "{doing} · {n} ouverts",
  },
  connection: "Connexion",
  numbered: "{name} ({n})",
  notice: {
    connecting: "Connexion…",
    ended: "Le shell s'est terminé",
    ended_with: "Le shell s'est terminé avec le statut {status}",
    lost: "La connexion au serveur a été perdue",
    sign_in: "Reconnectez-vous pour ouvrir un shell",
  },
  close: "Fermer ce shell",
  open: "Ouvrir un shell",
  none_menu: "Aucune de vos connexions n'a de shell",
  none_menu_hint: "Une connexion SSH en a un",
  none: "Aucune de vos connexions n'a de shell. Une connexion SSH en a un.",
  choose: "Aucun shell n'est ouvert. Choisissez la connexion sur laquelle en ouvrir un :",
  open_again: "Ouvrir à nouveau",
  unlock: "Déverrouiller la clé",
}
