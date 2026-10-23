/** Notificaciones y trabajo en curso en pantalla (shared/notifications, shared/operations). */
import type { Messages } from "../en"

export const notifications: Messages["notifications"] = {
  toasts: {
    more: "{n} más en Actividad",
    dismiss: "Descartar",
  },
  operations: {
    starting: "Iniciando",
    waiting_to_resume: "Esperando para reanudar",
    upload_sent: "Carga enviada; esperando al servidor",
  },
}
