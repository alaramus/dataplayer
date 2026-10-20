/** À quel serveur DataPlayer cet onglet parle (features/servers). */
import type { Messages } from "../en"

export const servers: Messages["servers"] = {
  check: {
    https_only: "Cette page utilise HTTPS. Utilisez une adresse de serveur HTTPS.",
    unreachable:
      "Un serveur DataPlayer compatible est injoignable. Vérifiez l'adresse, la version du serveur, le certificat et l'origine frontend autorisée (CORS).",
    incompatible: "Ce serveur n'est pas compatible avec cette version de DataPlayer.",
  },
  name_invalid: "Saisissez un nom de serveur de 1 à 100 caractères.",
  name: "Nom du serveur",
  url: "URL du serveur",
  url_example: "https://data.example.com",
  boundary: {
    title: "Se connecter à DataPlayer",
  },
  link: {
    new_server: "Nouveau serveur",
    connect_failed: "La connexion à ce serveur a échoué.",
    title: "Choisir le serveur pour ce lien",
    notice:
      "Ce lien utilise un autre serveur. Vérifiez l'adresse avant de vous connecter ; il se peut que vous deviez y ouvrir une session.",
    connect: "Vérifier et connecter",
  },
  switcher: {
    save_failed: "Le serveur n'a pas pu être enregistré dans ce navigateur.",
    compatible: "Serveur DataPlayer compatible.",
    saved: "Serveur enregistré. Choisissez « Connecter » pour l'utiliser dans cet onglet.",
    choose: "Choisir un serveur",
    servers: "Serveurs",
    intro: "Choisissez le serveur pour cet onglet du navigateur. Les comptes sont distincts sur chaque serveur.",
    current: "Actuel : {name} · {url}",
    current_mark: " · Actuel",
    check: "Vérifier",
    connect: "Connecter",
    edit: "Modifier le serveur",
    remove: "Supprimer le serveur",
    add: "Ajouter un serveur",
    check_connection: "Tester",
    save_and_connect: "Enregistrer et connecter",
    save: "Enregistrer le serveur",
  },
}
