/** L'âge des données, la fréquence de leur actualisation (shared/freshness). */
import type { Messages } from "../en"

export const freshness: Messages["freshness"] = {
  live: "En direct",
  nothing: "rien",
  read_now: "Lu à l'instant depuis la source.",
  read_ago: "Lu depuis la source il y a {age}.",
  keeps_as_source_says: "Cette connexion conserve les réponses aussi longtemps que la source l'indique.",
  keeps_nothing: "Cette connexion ne conserve rien : chaque lecture atteint la source.",
  keeps_for: "Cette connexion conserve les réponses pendant {window}.",
}
