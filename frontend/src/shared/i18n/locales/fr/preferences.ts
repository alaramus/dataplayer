import type { Messages } from "../en"

export const preferences: Messages["preferences"] = {
  title: "Préférences",
  saved: "Préférence enregistrée",
  not_saved: "La préférence n'a pas pu être enregistrée",
  sections: {
    general: "Général",
    general_summary: "Langue, thème, voix de lecture et visite de bienvenue",
    connections: "Connexions",
    connections_summary: "Fréquence de vérification des connexions pendant qu'un espace de travail est ouvert",
    ssh_keys: "Clés SSH",
    ssh_keys_summary: "Les clés que ce compte utilise pour les connexions SSH",
  },
  language_summary:
    "La langue de toute l'interface. Elle est conservée avec le compte et le suit dans chaque navigateur ; tant qu'aucune n'est choisie, celle du navigateur est utilisée.",
  appearance: "Apparence",
  appearance_summary:
    "Un thème clair ou sombre pour toute l'application, ou clair et sombre selon les changements du système d'exploitation. Conservé avec le compte, il le suit dans chaque navigateur.",
  voice: "Voix de lecture",
  voice_summary:
    "La voix qui lit les messages à voix haute, partout où ils sont lus. Les voix appartiennent à ce navigateur. Conservée dans ce navigateur.",
  tour: "Visite de bienvenue",
  tour_summary:
    "Les courts clips de la première visite, un pour chaque partie principale de l'application. Elle peut être rouverte ici à tout moment.",
  replay_tour: "Rejouer la visite",
  checks: "Vérifier que les connexions sont joignables",
  checks_summary:
    "Chaque connexion est sondée selon ce programme pendant qu'un espace de travail est ouvert, et le point à côté indique la dernière réponse. Une sonde ouvre sa propre connexion, aussi un serveur lent ou distant mérite d'être interrogé moins souvent.",
  checks_label: "Fréquence de vérification des connexions",
  interval: {
    off: "Jamais — uniquement lorsque je clique sur vérifier",
    "15s": "Toutes les 15 secondes",
    "30s": "Toutes les 30 secondes",
    "1m": "Chaque minute",
    "5m": "Toutes les 5 minutes",
    "15m": "Toutes les 15 minutes",
  },
}
