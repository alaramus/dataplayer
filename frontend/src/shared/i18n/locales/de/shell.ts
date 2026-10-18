/** Die Shell der Anwendung: App, Router, Stores, Sitzungen, Server, Sockets, Downloads, Zwischenablage. */
import type { Messages } from "../en"

export const shell: Messages["shell"] = {
  leave_work: {
    title: "Laufende Arbeit im Browser verlassen?",
    message:
      "Uploads und andere Arbeit, die in diesem Browser-Tab läuft, werden beim Wechseln beendet. Aufträge, die bereits dem Server gehören, laufen dort weiter.",
    confirm: "Server wechseln",
  },
  default_server: "Standardserver",
  server_url: {
    full_http: "Geben Sie eine vollständige HTTP- oder HTTPS-Server-URL ein.",
    full_url: "Geben Sie eine vollständige URL ein, etwa https://data.example.com.",
    http_only: "Verwenden Sie eine HTTP- oder HTTPS-Server-URL.",
    no_extras: "Die Server-URL darf keine Zugangsdaten, keine Abfrage und kein Fragment enthalten.",
    invalid_destination: "Ungültiges Ziel",
  },
  servers: {
    invalid_profile: "Geben Sie einen gültigen Servernamen und eine HTTP(S)-URL ein.",
    default_is_configured: "Der Standardserver wird von dieser Installation konfiguriert.",
    already_saved: "Dieser Server ist bereits gespeichert.",
    too_many: "Entfernen Sie einen gespeicherten Server, bevor Sie einen weiteren hinzufügen (höchstens {n}).",
  },
}
