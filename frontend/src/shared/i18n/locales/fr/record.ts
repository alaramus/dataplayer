/** Une ligne lue de haut en bas (features/record). */
import type { Messages } from "../en"

export const record: Messages["record"] = {
  columns: {
    keys: "Clé",
    name: "Colonne",
    type: "Type",
    value: "Valeur",
  },
  copied: "{name} copié",
  read_failed: "Impossible de lire cette ligne",
  no_row: "Aucune ligne ici",
  no_columns: "Aucune colonne",
  copy_value: "Copier cette valeur",
  navigation: "Navigation entre les lignes",
  previous: "Précédente",
  next: "Suivante",
}
