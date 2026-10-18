/** Das Protokoll des Servers (features/logs). */
import type { Messages } from "../en"

export const logs: Messages["logs"] = {
  logs: "Protokolle",
  tooltip: "Das Protokoll des Servers",
  levels: {
    all: "Alles",
    warning: "Warnungen und Fehler",
    error: "Fehler",
  },
  processes: {
    all: "Jeder Prozess",
    backend: "Backend",
    metrics: "Metriken",
    search_keeper: "Suchindex",
  },
  only_superuser: "Nur ein Superuser kann das Protokoll des Servers lesen.",
  search: "Im Text, in einer ref oder in einem Pfad suchen",
  follow: "Folgen",
  reload: "Das Protokoll erneut lesen",
  read_failed: "Das Protokoll konnte nicht gelesen werden",
  not_kept: "Dieser Server speichert keine Protokolldateien. Setzen Sie LOG_DIR, um sie zu speichern; bis dahin steht das Protokoll auf der Standardausgabe des Servers.",
  nothing: "Im Protokoll stimmt nichts überein.",
  ref: "ref {ref}",
  copy: "Diesen Eintrag kopieren",
  copied: "Kopiert",
  copy_refused: "Der Browser hat das Kopieren nicht erlaubt",
  older: "Ältere Einträge",
}
