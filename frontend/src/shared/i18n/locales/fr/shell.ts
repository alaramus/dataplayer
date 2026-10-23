/** La coquille de l'application : App, routeur, stores, sessions, serveurs, sockets, téléchargements, presse-papiers. */
import type { Messages } from "../en"

export const shell: Messages["shell"] = {
  leave_work: {
    title: "Quitter le travail en cours dans le navigateur ?",
    message:
      "Les téléversements et les autres travaux en cours dans cet onglet du navigateur s'arrêteront lors du changement. Les tâches dont le serveur est déjà propriétaire continueront là-bas.",
    confirm: "Changer de serveur",
  },
  default_server: "Serveur par défaut",
  server_url: {
    full_http: "Saisissez une URL de serveur HTTP ou HTTPS complète.",
    full_url: "Saisissez une URL complète, par exemple https://data.example.com.",
    http_only: "Utilisez une URL de serveur HTTP ou HTTPS.",
    no_extras: "L'URL du serveur ne doit contenir ni identifiants, ni requête, ni fragment.",
    invalid_destination: "Destination invalide",
  },
  servers: {
    invalid_profile: "Saisissez un nom de serveur et une URL HTTP(S) valides.",
    default_is_configured: "Le serveur par défaut est configuré par cette installation.",
    already_saved: "Ce serveur est déjà enregistré.",
    too_many: "Supprimez un serveur enregistré avant d'en ajouter un autre (maximum {n}).",
  },
}
