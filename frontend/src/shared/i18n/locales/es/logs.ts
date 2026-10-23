/** El registro del servidor (features/logs). */
import type { Messages } from "../en"

export const logs: Messages["logs"] = {
  logs: "Registros",
  tooltip: "El registro del servidor",
  levels: {
    all: "Todo",
    warning: "Advertencias y errores",
    error: "Errores",
  },
  processes: {
    all: "Todos los procesos",
    backend: "Back-end",
    metrics: "Métricas",
    search_keeper: "Índice de búsqueda",
  },
  only_superuser: "Solo un superusuario puede leer el registro del servidor.",
  search: "Buscar el texto, una referencia o una ruta",
  follow: "Seguir",
  reload: "Volver a leer el registro",
  read_failed: "No se pudo leer el registro",
  not_kept: "Este servidor no conserva archivos de registro. Define LOGRAR para conservarlos; hasta entonces, el registro está en la salida estándar del servidor.",
  nothing: "Nada del registro coincide.",
  ref: "Rey {ref}",
  copy: "Copiar esta entrada",
  copied: "Copiado",
  copy_refused: "El navegador no permitió copiar",
  older: "Entradas anteriores",
}
