import type { Messages } from "../en"

/** Comptes cloud avec lesquels les connexions se connectent (features/cloudAccounts). */
export const cloud_accounts: Messages["cloud_accounts"] = {
  section: {
    title: "Comptes cloud",
    hint: "Les comptes dont vos connexions obtiennent mots de passe et jetons : Amazon Web Services, Google Cloud, Microsoft Azure et HashiCorp Vault. Un jeton est émis pour chaque nouvelle connexion et jamais stocké. Les secrets saisis ici sont conservés chiffrés et ne sont plus jamais affichés.",
    form_hint: "Les comptes dont vos connexions obtiennent mots de passe et jetons ; un compte sert à n'importe quelle connexion. Ses secrets sont conservés chiffrés et ne sont plus jamais affichés.",
    new_account: "Nouveau compte",
    empty: "Aucun compte cloud pour l'instant",
    unused: "Aucune connexion ne l'utilise",
    used_by: "Utilisé par {names}",
    ambient: "Identité de ce serveur",
    test: "Tester le compte",
    test_failed: "Le compte n'a pas pu être testé",
    edit: "Modifier le compte",
    delete_title: "Supprimer ce compte ?",
    delete_message: "{name} et ses secrets disparaîtront de ce serveur. Les identifiants eux-mêmes restent dans le cloud.",
    delete: "Supprimer",
    delete_failed: "Le compte n'a pas pu être supprimé",
    delete_used: "Dirigez d'abord ses connexions vers un autre compte",
    delete_account: "Supprimer ce compte",
  },
  dialog: {
    title_new: "Nouveau compte cloud",
    title_edit: "Modifier le compte cloud",
    subtitle: "Les secrets sont conservés chiffrés et ne sont plus jamais affichés",
    name: "Nom",
    kind: "Cloud",
    make: "Créer",
    save: "Enregistrer",
    made: "Compte créé",
    saved: "Compte enregistré",
    save_failed: "Le compte n'a pas pu être enregistré",
  },
}
