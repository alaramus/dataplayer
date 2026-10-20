/** Formulaires dessinés à partir d'un schéma JSON (shared/SchemaForm). */
import type { Messages } from "../en"

export const schema_form: Messages["schema_form"] = {
  hidden: "<masqué>",
  show_password: "Afficher le mot de passe",
  hide_password: "Masquer le mot de passe",
  choose: "Choisir « {label} »",
  is_number: "« {label} » est un nombre",
  at_least: "« {label} » vaut au moins {n}",
  at_most: "« {label} » vaut au plus {n}",
  required: "« {label} » est requis",
  min_length: "« {label} » compte au moins {n} caractère | « {label} » compte au moins {n} caractères",
}
