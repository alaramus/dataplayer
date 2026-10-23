/** A qué servidor de DataPlayer habla esta pestaña (features/servers). */
import type { Messages } from "../en"

export const servers: Messages["servers"] = {
  check: {
    https_only: "Esta página usa HTTPS. Usa una dirección de servidor HTTPS.",
    unreachable:
      "No se pudo llegar a un servidor de DataPlayer compatible. Comprueba la dirección, la versión del servidor, el certificado y el origen del front-end permitido (CORS).",
    incompatible: "Este servidor no es compatible con esta versión de DataPlayer.",
  },
  name_invalid: "Introduce un nombre de servidor de 1 a 100 caracteres.",
  name: "Nombre del servidor",
  url: "URL del servidor",
  url_example: "https://data.example.com",
  boundary: {
    title: "Conectar con DataPlayer",
  },
  link: {
    new_server: "Nuevo servidor",
    connect_failed: "No se pudo conectar con este servidor.",
    title: "Elegir el servidor para este enlace",
    notice:
      "Este enlace usa otro servidor. Comprueba la dirección antes de conectarte; puede que tengas que iniciar sesión allí.",
    connect: "Comprobar y conectar",
  },
  switcher: {
    save_failed: "No se pudo guardar el servidor en este navegador.",
    compatible: "Servidor de DataPlayer compatible.",
    saved: "Servidor guardado. Elige Conectar para usarlo en esta pestaña.",
    choose: "Elegir servidor",
    servers: "Servidores",
    intro: "Elige el servidor para esta pestaña del navegador. Las cuentas son independientes en cada servidor.",
    current: "Actual: {name} · {url}",
    current_mark: " · Actual",
    check: "Comprobar",
    connect: "Conectar",
    edit: "Editar servidor",
    remove: "Quitar servidor",
    add: "Añadir servidor",
    check_connection: "Comprobar la conexión",
    save_and_connect: "Guardar y conectar",
    save: "Guardar servidor",
  },
}
