/** La antigüedad de los datos y su frecuencia de actualización (shared/freshness). */
import type { Messages } from "../en"

export const freshness: Messages["freshness"] = {
  live: "En vivo",
  nothing: "nada",
  read_now: "Leído de la fuente ahora mismo.",
  read_ago: "Leído de la fuente hace {age}.",
  keeps_as_source_says: "Esta conexión conserva las respuestas durante el tiempo que indique la fuente.",
  keeps_nothing: "Esta conexión no conserva nada: cada lectura llega a la fuente.",
  keeps_for: "Esta conexión conserva las respuestas durante {window}.",
}
