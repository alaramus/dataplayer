/** El armazón de la aplicación: App, enrutador, stores, sesiones, servidores, sockets, descargas, portapapeles. */
import type { Messages } from "../en"

export const shell: Messages["shell"] = {
  leave_work: {
    title: "¿Abandonar el trabajo en curso del navegador?",
    message:
      "Las cargas y demás trabajo en ejecución en esta pestaña del navegador se detendrán al cambiar. Las tareas que ya pertenecen al servidor continuarán allí.",
    confirm: "Cambiar de servidor",
  },
  default_server: "Servidor predeterminado",
  server_url: {
    full_http: "Introduce una URL de servidor HTTP o HTTPS completa.",
    full_url: "Introduce una URL completa, como https://data.example.com.",
    http_only: "Usa una URL de servidor HTTP o HTTPS.",
    no_extras: "La URL del servidor no debe contener credenciales, una consulta ni un fragmento.",
    invalid_destination: "Destino no válido",
  },
  servers: {
    invalid_profile: "Introduce un nombre de servidor y una URL HTTP(S) válidos.",
    default_is_configured: "La instalación configura el servidor predeterminado.",
    already_saved: "Ese servidor ya está guardado.",
    too_many: "Quita un servidor guardado antes de añadir otro (máximo {n}).",
  },
}
