/** Una fila leída hacia abajo (features/record). */
import type { Messages } from "../en"

export const record: Messages["record"] = {
  columns: {
    keys: "Clave",
    name: "Columna",
    type: "Tipo",
    value: "Valor",
  },
  copied: "{name} copiado",
  read_failed: "No se pudo leer esta fila",
  no_row: "No hay ninguna fila aquí",
  no_columns: "Sin columnas",
  copy_value: "Copiar este valor",
  navigation: "Navegación entre filas",
  previous: "Anterior",
  next: "Siguiente",
}
