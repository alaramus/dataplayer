/** Le journal du serveur (features/logs). */
import type { Messages } from "../en"

export const logs: Messages["logs"] = {
  logs: "Journaux",
  tooltip: "Le journal du serveur",
  levels: {
    all: "Tout",
    warning: "Avertissements et erreurs",
    error: "Erreurs",
  },
  processes: {
    all: "Tous les processus",
    backend: "Backend",
    metrics: "Métriques",
    search_keeper: "Index de recherche",
  },
  only_superuser: "Seul un superutilisateur peut lire le journal du serveur.",
  search: "Rechercher dans le texte, une ref ou un chemin",
  follow: "Suivre",
  reload: "Relire le journal",
  read_failed: "Le journal n'a pas pu être lu",
  not_kept: "Ce serveur ne conserve aucun fichier de journal. Définissez LOG_DIR pour les conserver ; d'ici là, le journal se trouve sur la sortie standard du serveur.",
  nothing: "Rien dans le journal ne correspond.",
  ref: "ref {ref}",
  copy: "Copier cette entrée",
  copied: "Copié",
  copy_refused: "Le navigateur n'a pas autorisé la copie",
  older: "Entrées plus anciennes",
}
