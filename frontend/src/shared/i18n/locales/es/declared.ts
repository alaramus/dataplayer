/** Referencias que alguien trazó entre dos columnas (features/declared). */
import type { Messages } from "../en"

export const declared: Messages["declared"] = {
  title: "Referencias declaradas",
  declare_one: "Declarar una referencia",
  read_failed: "No se pudieron leer las referencias trazadas desde este nodo",
  none: "Ninguna",
  remove_tooltip: "Quitar esta referencia",
  remove: {
    title: "¿Quitar esta referencia?",
    message: "{from} → {to} deja de ofrecerse aquí y en el otro extremo. Ninguna de las dos fuentes cambia.",
    confirm: "Quitar",
    done: "Referencia declarada eliminada",
    failed: "No se pudo quitar esta referencia",
  },
  dialog: {
    subtitle: "Desde una columna de {node} hasta una columna de cualquier otro lugar",
    near: "Esta columna",
    points_at: "Apunta a",
    far: "Esa columna",
    declare: "Declarar",
    read_failed: "No se pudo leer este nodo como filas",
    failed: "No se pudo declarar esta referencia",
  },
}
