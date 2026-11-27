/** Formularios generados a partir de un esquema JSON (shared/SchemaForm). */
import type { Messages } from "../en"

export const schema_form: Messages["schema_form"] = {
  hidden: "<oculto>",
  show_password: "Mostrar la contraseña",
  hide_password: "Ocultar la contraseña",
  choose: "Elegir {label}",
  is_number: "{label} es un número",
  at_least: "{label} es al menos {n}",
  at_most: "{label} es como máximo {n}",
  required: "{label} es obligatorio",
  min_length: "{label} debe tener al menos {n} carácter | {label} debe tener al menos {n} caracteres",
  from_file: "Leer {label} desde un archivo",
  file_too_large: "{label}: este archivo es mucho mayor que un certificado o una clave; elija el archivo en sí",
  file_not_text: "{label}: este archivo no es texto. Elija el archivo PEM o JSON, no uno binario",
  file_too_long: "{label}: el archivo contiene más de {n} caracteres, más de los que admite el campo",
}
