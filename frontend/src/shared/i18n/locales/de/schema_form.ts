/** Formulare, die aus einem JSON-Schema gezeichnet werden (shared/SchemaForm). */
import type { Messages } from "../en"

export const schema_form: Messages["schema_form"] = {
  hidden: "<verborgen>",
  show_password: "Passwort anzeigen",
  hide_password: "Passwort verbergen",
  choose: "„{label}“ auswählen",
  is_number: "„{label}“ ist eine Zahl",
  at_least: "„{label}“ ist mindestens {n}",
  at_most: "„{label}“ ist höchstens {n}",
  required: "„{label}“ ist erforderlich",
  min_length: "„{label}“ umfasst mindestens {n} Zeichen | „{label}“ umfasst mindestens {n} Zeichen",
  from_file: "„{label}“ aus einer Datei lesen",
  file_too_large: "„{label}“: Diese Datei ist weit größer als ein Zertifikat oder ein Schlüssel; wählen Sie die Datei selbst",
  file_not_text: "„{label}“: Diese Datei ist kein Text. Wählen Sie die PEM- oder JSON-Datei, keine Binärdatei",
  file_too_long: "„{label}“: Die Datei enthält mehr als {n} Zeichen, mehr als das Feld aufnimmt",
}
