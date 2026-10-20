/** La visite de bienvenue (features/onboarding), et les quelques mots de la
    fenêtre du guide (features/guide) et de la lecture à voix haute (features/speech). */
import type { Messages } from "../en"

export const onboarding: Messages["onboarding"] = {
  title: "Bienvenue dans DataPlayer",
  intro: "Choisissez une langue et l'apparence de l'application, puis faites une courte visite de ce qu'elle sait faire : un clip silencieux pour chacune de ses parties principales.",
  steps: {
    new_connection: "Créer une nouvelle connexion",
    tabs: "Travailler avec les onglets",
    table: "Travailler avec les tables",
    pipelines: "Travailler avec les pipelines",
    dashboards: "Travailler avec les tableaux de bord",
    ai_agent: "Travailler avec l'agent IA",
  },
  position: "Étape {n} sur {total}",
  start: "Démarrer la visite",
  finish: "Terminer",
  next: "Suivant",
  skip_tour: "Ignorer la visite",
  skip: "Ignorer",
  mark_failed: "La visite n'a pas pu être marquée comme vue",
  close_title: "Fermer la visite de bienvenue ?",
  close_message: "La visite ne s'ouvrira plus toute seule. Vous pouvez la rejouer à tout moment dans les Préférences, sous Visite de bienvenue.",
  close_confirm: "Fermer la visite",
  keep_watching: "Continuer à regarder",
  guide: {
    title: "Guide",
    not_a_page: "Ce lien ne mène pas à une page du guide",
    read_failed: "Cette page du guide n'a pas pu être lue",
  },
  speech: {
    listen: "Écouter",
    stop: "Arrêter la lecture à voix haute",
    browser_default: "Par défaut du navigateur",
  },
}
