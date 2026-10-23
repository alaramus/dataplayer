/** Eine Zeile, von oben nach unten gelesen (features/record). */
import type { Messages } from "../en"

export const record: Messages["record"] = {
  columns: {
    keys: "Schlüssel",
    name: "Spalte",
    type: "Typ",
    value: "Wert",
  },
  copied: "{name} kopiert",
  read_failed: "Diese Zeile konnte nicht gelesen werden",
  no_row: "Hier ist keine Zeile",
  no_columns: "Keine Spalten",
  copy_value: "Diesen Wert kopieren",
  navigation: "Zeilennavigation",
  previous: "Vorherige",
  next: "Nächste",
}
