/** Die eigenen Wörter des Komponenten-Kits: leere Zustände, Kopierknöpfe, Auswahlfelder (shared/ui). */
import type { Messages } from "../en"

export const kit: Messages["kit"] = {
  copy: {
    tooltip: "Kopieren",
  },
  color_picker: {
    reset: "Farbe zurücksetzen",
  },
  file: {
    choose_one: "Eine Datei auswählen",
    choose_many: "Dateien auswählen",
  },
  date_time: {
    pick: "Tag und Uhrzeit in UTC auswählen",
  },
  fullscreen: {
    enter: "Den Bildschirm füllen",
    leave: "Vollbild verlassen",
    unsupported: "Dieser Browser kann den Bildschirm nicht füllen",
  },
  layout: {
    user_menu: "Benutzermenü",
    preferences: "Einstellungen",
    admin: "Verwaltung",
    sign_out: "Abmelden",
  },
  option: {
    clear: "Leeren",
  },
  progress: {
    paused: "Pausiert",
  },
  table: {
    empty: "Nichts anzuzeigen",
  },
  tree: {
    tick: "„{name}“ markieren",
  },
}
