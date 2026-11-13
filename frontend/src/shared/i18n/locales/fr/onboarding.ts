/** La visite de bienvenue (features/onboarding), et les quelques mots de la
    fenêtre du guide (features/guide) et de la lecture à voix haute (features/speech). */
import type { Messages } from "../en"

export const onboarding: Messages["onboarding"] = {
  title: "Bienvenue dans DataPlayer",
  intro: "Choisissez une langue et l'apparence de l'application.",
  tour_offer: "Ensuite, faites une visite de trois minutes : vous créez une petite base de données, travaillez avec elle puis la retirez, avec un conseil à côté de chaque bouton à presser.",
  position: "Étape {n} sur {total}",
  finish: "Terminer",
  next: "Suivant",
  take_tour: "Faire la visite",
  look_around: "Explorer seul",
  mark_failed: "La visite n'a pas pu être marquée comme vue",
  close_title: "Terminer la visite ?",
  close_message: "La visite ne s'ouvrira plus d'elle-même. Vous pouvez la faire à tout moment dans les Préférences, sous Visites.",
  close_confirm: "Terminer la visite",
  keep_going: "Continuer",
  end_tour: "Terminer la visite",
  more_tours: "Voir d'autres visites",
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
    service: {
      title: "Un serveur, démarré ici",
      add: "Appuyez encore une fois sur +.",
      pick: "Choisissez Redis : rien jusqu'ici ne lui ressemblait.",
      start: "Ce bouton démarre Redis ici même, dans Docker, avec des données pour l'essayer, et crée sa connexion pour vous. Tout serveur de ce catalogue doté d'un tel bouton démarre de la même façon. La visite s'arrête là : la fenêtre est à vous.",
    },
  },
  tours: {
    basics: {
      title: "Les bases",
      summary: "Créer une base de données, travailler avec elle et la retirer.",
    },
    practice_name: "practice",
    folder_name: "Mes fichiers",
    preparing: "Création d'une base d'entraînement pour cette visite…",
    setup_failed: "La visite n'a pas pu préparer sa base d'entraînement",
    cleanup_failed: "La visite n'a pas pu retirer sa base d'entraînement",
    list: {
      take: "Faire",
      again: "Refaire",
    },
    views: {
      title: "Une table, lue autrement",
      summary: "La même table en graphique, en structure et en documents.",
      back: "Revenez à l'onglet {table}.",
      open: {
        title: "Ouvrir la table d'entraînement",
        connection: "La visite a créé cette base d'entraînement. Ouvrez-la.",
        table: "Ouvrez {table}.",
      },
      chart: {
        title: "En graphique",
        hint: "Dessinez la page en graphique.",
      },
      structure: {
        title: "En structure",
        hint: "Voyez les colonnes, clés et index de la table.",
      },
      document: {
        title: "En documents",
        hint: "Lisez les lignes comme des documents plutôt qu'en grille.",
      },
      closing: {
        title: "Terminé",
        text: "La base d'entraînement est retirée quand vous fermez ceci.",
      },
    },
    pipeline: {
      title: "Un pipeline",
      summary: "Les lignes d'une table enregistrées en fichier CSV dans votre dossier.",
      new: {
        title: "Un nouveau pipeline",
        space: "Ouvrez les pipelines.",
        create: "Créez un nouveau pipeline.",
      },
      source: {
        title: "D'où viennent les lignes",
        connection: "Appuyez sur la base d'entraînement : ses tables s'ouvrent à côté du canevas.",
        schema: "Ouvrez main, l'unique schéma de SQLite.",
        tick: "Cochez {table}.",
        done: "Posez-la sur le canevas.",
      },
      target: {
        title: "Où elles vont",
        connection: "Appuyez maintenant sur votre dossier.",
        top: "Cochez le dossier lui-même.",
        done: "Posez-le sur le canevas.",
      },
      link: {
        title: "Reliez-les",
        hint: "Faites glisser la ligne de {table} sur la ligne du dossier. Les lignes où elle peut aller s'allument.",
      },
      run: {
        title: "Lancez-le",
        menu: "Ouvrez le menu à côté de « Activer ».",
        hint: "Exécutez-le une fois maintenant. Le lien enregistre la table en fichier CSV.",
        taken: "Le dossier contient déjà un fichier de ce nom : sous « Si le nom est pris », choisissez « Garder les deux », puis exécutez-le une fois de plus.",
      },
      seen: {
        title: "Le fichier",
        space: "Revenez à Données.",
        folder: "Ouvrez votre dossier.",
        file: "Voici le CSV fait par le pipeline. La base d'entraînement s'en va à la fin ; le fichier reste.",
      },
    },
    dashboards: {
      title: "Tableaux de bord",
      summary: "Où se créent les tableaux de bord et d'où viennent leurs métriques.",
      space: {
        title: "Tableaux de bord",
        hint: "Ouvrez les tableaux de bord.",
      },
      new: {
        title: "Un tableau de bord",
        hint: "Un tableau de bord commence ici : graphiques et tuiles de métriques sur une grille.",
        store: "Les tableaux de bord gardent leurs métriques dans un stockage qu'un administrateur démarre une fois, ici.",
      },
      agent: {
        title: "Les métriques d'un agent",
        open: "Ouvrez les sources de métriques.",
        view: "Les agents rendent compte des machines où ils tournent.",
        register: "Enregistrez un agent ici : vous obtenez sa clé et un fichier Docker Compose qui le démarre sur la machine à surveiller.",
      },
      connections: {
        title: "Les métriques de vos connexions",
        view: "Vos connexions peuvent aussi rendre compte d'elles-mêmes.",
        switch: "Choisissez une connexion et activez-la : PostgreSQL, MySQL et Redis envoient leurs propres métriques.",
      },
    },
    agent: {
      title: "L'agent IA",
      summary: "Où se choisissent la clé, le modèle et le contexte de l'agent.",
      space: {
        title: "L'agent",
        hint: "Ouvrez l'espace IA.",
      },
      chat: {
        title: "Une discussion",
        hint: "Commencez une nouvelle discussion.",
        close: "Fermez les réglages pour revenir aux discussions.",
      },
      key: {
        title: "Sa clé",
        open: "Ouvrez les réglages IA.",
        hint: "Le modèle par défaut se choisit ici, avec à côté le bouton de clé : l'agent travaille avec votre clé d'un fournisseur, Anthropic, OpenAI et d'autres.",
      },
      model: {
        title: "Son modèle",
        hint: "Choisissez le modèle de la discussion.",
      },
      attach: {
        title: "Ce qu'il sait",
        hint: "Joignez une table, un onglet ou un nœud : l'agent lit de quoi vous parlez au lieu de deviner.",
      },
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
