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
}
