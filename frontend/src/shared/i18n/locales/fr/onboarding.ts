/** La visite de bienvenue (features/onboarding), et les quelques mots de la
    fenêtre du guide (features/guide) et de la lecture à voix haute (features/speech). */
import type { Messages } from "../en"

export const onboarding: Messages["onboarding"] = {
  title: "Bienvenue dans DataPlayer",
  intro: "Choisissez une langue et l'apparence de l'application.",
  tour_offer: "Ensuite, faites une visite de trois minutes : vous créez une petite base de données, travaillez avec elle puis la retirez, avec un conseil à côté de chaque bouton à presser.",
  position: "Étape {n} sur {total}",
  finish: "Terminer",
  take_tour: "Faire la visite",
  look_around: "Explorer seul",
  mark_failed: "La visite n'a pas pu être marquée comme vue",
  close_title: "Terminer la visite ?",
  close_message: "La visite ne s'ouvrira plus d'elle-même. Vous pouvez la faire à tout moment dans les Préférences, sous Visite de bienvenue.",
  close_confirm: "Terminer la visite",
  keep_going: "Continuer",
  end_tour: "Terminer la visite",
  tour: {
    make: {
      title: "Créer une base de données",
      add: "Appuyez sur + pour ajouter une connexion.",
      pick: "Choisissez SQLite.",
      here: "SQLite n'a pas besoin de serveur : créez une base de données ici même, dans votre propre stockage.",
      submit: "Gardez ce qui est proposé, un fichier avec des données d'exemple, et créez-le.",
    },
    open: {
      title: "Ouvrir une table",
      connection: "Ouvrez la nouvelle connexion pour voir ses tables.",
      table: "Ouvrez la table {table}.",
    },
    filter: {
      title: "Filtrer les lignes",
      open: "Ouvrez les filtres.",
      fill: "N'affichez que les tâches bloquées : colonne status, égal à, blocked. Puis appliquez.",
    },
    edit: {
      title: "Modifier une valeur",
      cell: "Double-cliquez sur le titre d'une tâche pour le modifier.",
      save: "Écrivez un nouveau titre et enregistrez-le. La modification va directement dans la base.",
    },
    query: {
      title: "Exécuter une requête",
      open: "Ouvrez cette table comme requête : la console reçoit un SELECT écrit pour elle.",
      run: "Exécutez-la. On peut écrire ici n'importe quel SQL.",
    },
    disconnect: {
      title: "Supprimer la connexion",
      edit: "Ouvrez les réglages de la connexion.",
      delete: "Supprimez la connexion.",
      confirm: "Confirmez. Seule la connexion s'en va : le fichier de la base reste dans votre stockage.",
    },
    folder: {
      title: "Connecter votre propre dossier",
      add: "Appuyez de nouveau sur +.",
      pick: "Choisissez Fichiers.",
      create: "Créez la connexion.",
      save: "Le chemin / est tout votre stockage personnel. Enregistrez la connexion.",
    },
    find: {
      title: "Trouver le fichier",
      connection: "Ouvrez la connexion au dossier.",
      folder: "Ouvrez {folder} : la base que vous avez créée s'y trouve.",
    },
    remove: {
      title: "Supprimer le fichier",
      tick: "Cochez {file}.",
      actions: "Ouvrez le menu des actions.",
      delete: "Choisissez Supprimer.",
      confirm: "Confirmez. Il ne reste rien de la démonstration, et la connexion au dossier reste à vous.",
    },
    finished: {
      title: "Vous avez les bases",
      text: "Connexions, tables, filtres, modifications, requêtes et votre propre stockage. Les pipelines, les tableaux de bord et l'agent IA sont dans la barre de gauche. La visite est dans les Préférences quand vous voulez la refaire.",
    },
  },
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
