/** Des mots qui n'appartiennent à aucun écran : la connexion, la langue, les thèmes. */
import type { Messages } from "../en"

export const common: Messages["common"] = {
  back_to_workspace: "Retour à l'espace de travail",
}

export const language: Messages["language"] = {
  label: "Langue",
  browser: "La langue du navigateur",
  browser_hint: "La langue demandée par ce navigateur, ou l'anglais",
}

export const auth: Messages["auth"] = {
  sign_in: "Se connecter",
  email: "E-mail",
  password: "Mot de passe",
  email_required: "L'e-mail est requis",
  password_required: "Le mot de passe est requis",
  checking_server: "Vérification du serveur…",
  retry_connection: "Réessayer la connexion",
  sign_in_failed: "Connexion impossible. Vérifiez l'e-mail et le mot de passe.",
  welcome_tagline: "Un seul endroit pour chaque source de données avec laquelle vous travaillez",
  set_password: {
    title: "Choisissez votre mot de passe",
    for_whom: "Pour {email}",
    new: "Nouveau mot de passe",
    repeat: "Répétez le mot de passe",
    too_short: "Au moins {n} caractère | Au moins {n} caractères",
    mismatch: "Les deux mots de passe diffèrent",
    submit: "Définir le mot de passe",
    done: "Mot de passe défini. Connectez-vous avec.",
    checking: "Vérification du lien…",
    invalid: "Ce lien ne fonctionne plus : il a été utilisé, il a expiré ou un plus récent a été émis. Demandez-en un nouveau à votre administrateur.",
    to_sign_in: "Aller à la connexion",
  },
}

export const theme: Messages["theme"] = {
  label: "Thème",
  light: "Clair",
  paper_light: "Papier clair",
  paper_light_hint: "Papier clair et chaud avec un accent bronze",
  dark: "Sombre",
  paper: "Papier sombre",
  paper_hint: "Papier sombre et chaud avec un accent bronze",
  midnight: "Minuit",
  midnight_hint: "Le plus sombre : bleu nuit presque noir avec un accent bleu glacé",
  dark_blue: "Bleu sombre",
  dark_blue_hint: "Bleu marine saturé avec un accent cyan",
  dark_purple: "Violet sombre",
  dark_purple_hint: "Néon violet avec des accents rose et cyan",
  system: "Système",
  system_hint: "Clair ou sombre, selon le changement du système d'exploitation",
  switch_to: "Passer à {theme}",
}
