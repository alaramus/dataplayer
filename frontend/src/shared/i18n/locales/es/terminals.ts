/** Terminales (features/terminals). */
import type { Messages } from "../en"

export const terminals: Messages["terminals"] = {
  terminals: "Terminales",
  press: {
    hide: "Ocultar las terminales",
    open: "Abrir una terminal",
    open_on: "Abrir una terminal en {name}",
    on: "Terminal en {name}",
    with_open: "{doing} · {n} abiertas",
  },
  connection: "Conexión",
  numbered: "{name} ({n})",
  notice: {
    connecting: "Conectando…",
    ended: "El Shell ha terminado",
    ended_with: "El Shell ha terminado con el estado {status}",
    lost: "Se perdió la conexión con el servidor",
    sign_in: "Vuelve a iniciar sesión para abrir una terminal",
  },
  close: "Cerrar esta terminal",
  open: "Abrir una terminal",
  none_menu: "Ninguna de tus conexiones tiene terminal",
  none_menu_hint: "Una conexión SSH sí",
  none: "Ninguna de tus conexiones tiene terminal. Una conexión SSH sí.",
  choose: "No hay ninguna terminal abierta. Elige la conexión en la que abrir una:",
  open_again: "Abrir de nuevo",
  unlock: "Desbloquear la clave",
}
