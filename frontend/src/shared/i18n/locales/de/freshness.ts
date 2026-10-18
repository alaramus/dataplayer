/** Wie alt Daten sind, wie oft sie aktualisiert werden (shared/freshness). */
import type { Messages } from "../en"

export const freshness: Messages["freshness"] = {
  live: "Live",
  nothing: "nichts",
  read_now: "Gerade eben aus der Quelle gelesen.",
  read_ago: "Vor {age} aus der Quelle gelesen.",
  keeps_as_source_says: "Diese Verbindung hält Antworten so lange, wie die Quelle angibt.",
  keeps_nothing: "Diese Verbindung hält nichts: Jedes Lesen erreicht die Quelle.",
  keeps_for: "Diese Verbindung hält Antworten für {window}.",
}
