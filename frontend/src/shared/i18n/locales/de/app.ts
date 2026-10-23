/** Wörter, die zu keinem Bildschirm gehören: die Anmeldung, die Sprache, die Designs. */
import type { Messages } from "../en"

export const common: Messages["common"] = {
  back_to_workspace: "Zurück zum Arbeitsbereich",
}

export const language: Messages["language"] = {
  label: "Sprache",
  browser: "Die Sprache des Browsers",
  browser_hint: "Welche Sprache dieser Browser auch anfordert, oder Englisch",
}

export const auth: Messages["auth"] = {
  sign_in: "Anmelden",
  email: "E-Mail",
  password: "Passwort",
  email_required: "E-Mail ist erforderlich",
  password_required: "Passwort ist erforderlich",
  checking_server: "Server wird geprüft…",
  retry_connection: "Verbindung erneut versuchen",
  sign_in_failed: "Anmeldung nicht möglich. Prüfen Sie E-Mail und Passwort.",
  welcome_tagline: "Ein Ort für jede Datenquelle, mit der Sie arbeiten",
}

export const theme: Messages["theme"] = {
  label: "Design",
  light: "Hell",
  paper_light: "Helles Papier",
  paper_light_hint: "Warmes helles Papier mit Bronze-Akzent",
  dark: "Dunkel",
  paper: "Dunkles Papier",
  paper_hint: "Warmes dunkles Papier mit Bronze-Akzent",
  midnight: "Mitternacht",
  midnight_hint: "Am dunkelsten: fast schwarzes Marineblau mit eisblauem Akzent",
  dark_blue: "Dunkelblau",
  dark_blue_hint: "Sattes Marineblau mit türkisfarbenem Akzent",
  dark_purple: "Dunkelviolett",
  dark_purple_hint: "Violettes Neon mit rosa und türkisfarbenen Akzenten",
  system: "System",
  system_hint: "Hell oder Dunkel, wie das Betriebssystem wechselt",
  switch_to: "Zu {theme} wechseln",
}
