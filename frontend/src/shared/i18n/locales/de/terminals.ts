/** Terminals (features/terminals). */
import type { Messages } from "../en"

export const terminals: Messages["terminals"] = {
  terminals: "Terminals",
  press: {
    hide: "Die Terminals ausblenden",
    open: "Ein Terminal öffnen",
    open_on: "Ein Terminal auf „{name}“ öffnen",
    on: "Terminal auf „{name}“",
    with_open: "{doing} · {n} offen",
  },
  connection: "Verbindung",
  numbered: "{name} ({n})",
  notice: {
    connecting: "Verbindung wird hergestellt…",
    ended: "Die Shell wurde beendet",
    ended_with: "Die Shell wurde mit Status {status} beendet",
    lost: "Die Verbindung zum Server wurde unterbrochen",
    sign_in: "Melden Sie sich erneut an, um ein Terminal zu öffnen",
  },
  close: "Dieses Terminal schließen",
  open: "Ein Terminal öffnen",
  none_menu: "Keine Ihrer Verbindungen hat ein Terminal",
  none_menu_hint: "Eine SSH-Verbindung hat eines",
  none: "Keine Ihrer Verbindungen hat ein Terminal. Eine SSH-Verbindung hat eines.",
  choose: "Kein Terminal ist geöffnet. Wählen Sie die Verbindung, auf der eines geöffnet werden soll:",
  open_again: "Erneut öffnen",
  unlock: "Den Schlüssel entsperren",
}
