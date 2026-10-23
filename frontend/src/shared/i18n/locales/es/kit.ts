/** Las palabras propias del kit de componentes: estados vacíos, botones de copia, selectores (shared/ui). */
import type { Messages } from "../en"

export const kit: Messages["kit"] = {
  copy: {
    tooltip: "Copiar",
  },
  color_picker: {
    reset: "Restablecer el color",
  },
  file: {
    choose_one: "Elige un archivo",
    choose_many: "Elige archivos",
  },
  date_time: {
    pick: "Elige un día y una hora, en UTC",
  },
  fullscreen: {
    enter: "Pantalla completa",
    leave: "Salir de pantalla completa",
    unsupported: "Este navegador no puede usar la pantalla completa",
  },
  layout: {
    user_menu: "Menú de usuario",
    preferences: "Preferencias",
    admin: "Administración",
    sign_out: "Cerrar sesión",
  },
  option: {
    clear: "Borrar",
  },
  progress: {
    paused: "En pausa",
  },
  table: {
    empty: "No hay nada que mostrar",
  },
  tree: {
    tick: "Marcar {name}",
  },
}
