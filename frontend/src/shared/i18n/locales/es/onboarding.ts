/** El recorrido de bienvenida (features/onboarding), y las pocas palabras de la
    ventana de la guía (features/guide) y de la lectura en voz alta (features/speech). */
import type { Messages } from "../en"

export const onboarding: Messages["onboarding"] = {
  title: "Te damos la bienvenida a DataPlayer",
  intro: "Elige un idioma y el aspecto de la aplicación.",
  tour_offer: "Después, haz un recorrido de tres minutos: crearás una pequeña base de datos, trabajarás con ella y la quitarás, con una pista junto a cada botón que hay que pulsar.",
  position: "Paso {n} de {total}",
  finish: "Terminar",
  take_tour: "Hacer el recorrido",
  look_around: "Explorar por mi cuenta",
  mark_failed: "No se pudo marcar el recorrido como visto",
  close_title: "¿Terminar el recorrido?",
  close_message: "El recorrido no volverá a abrirse solo. Puedes hacerlo cuando quieras en Preferencias, en Recorrido de bienvenida.",
  close_confirm: "Terminar recorrido",
  keep_going: "Seguir",
  end_tour: "Terminar recorrido",
  tour: {
    make: {
      title: "Crea una base de datos",
      add: "Pulsa + para añadir una conexión.",
      pick: "Elige SQLite.",
      here: "SQLite no necesita servidor: crea una base de datos aquí mismo, en tu propio almacenamiento.",
      submit: "Deja lo que se ofrece, un archivo con datos de ejemplo, y créalo.",
    },
    open: {
      title: "Abre una tabla",
      connection: "Abre la nueva conexión para ver sus tablas.",
      table: "Abre la tabla {table}.",
    },
    filter: {
      title: "Filtra las filas",
      open: "Abre los filtros.",
      fill: "Muestra solo las tareas bloqueadas: columna status, igual a, blocked. Luego aplica.",
    },
    edit: {
      title: "Cambia un valor",
      cell: "Haz doble clic en el título de una tarea para cambiarlo.",
      save: "Escribe un título nuevo y guárdalo. El cambio va directo a la base de datos.",
    },
    query: {
      title: "Ejecuta una consulta",
      open: "Abre esta tabla como consulta: la consola recibe un SELECT escrito para ella.",
      run: "Ejecútala. Aquí se puede escribir cualquier SQL.",
    },
    disconnect: {
      title: "Elimina la conexión",
      edit: "Abre los ajustes de la conexión.",
      delete: "Elimina la conexión.",
      confirm: "Confirma. Solo se va la conexión: el archivo de la base de datos sigue en tu almacenamiento.",
    },
    folder: {
      title: "Conecta tu propia carpeta",
      add: "Pulsa + otra vez.",
      pick: "Elige Archivos.",
      create: "Crea la conexión.",
      save: "La ruta / es todo tu almacenamiento personal. Guarda la conexión.",
    },
    find: {
      title: "Encuentra el archivo",
      connection: "Abre la conexión de la carpeta.",
      folder: "Abre {folder}: ahí está la base de datos que creaste.",
    },
    remove: {
      title: "Elimina el archivo",
      tick: "Marca {file}.",
      actions: "Abre el menú de acciones.",
      delete: "Elige Eliminar.",
      confirm: "Confirma. No queda nada de la demostración, y la conexión de la carpeta sigue siendo tuya.",
    },
    finished: {
      title: "Ya conoces lo básico",
      text: "Conexiones, tablas, filtros, cambios, consultas y tu propio almacenamiento. Las canalizaciones, los paneles y el agente de IA están en la barra de la izquierda. El recorrido está en Preferencias siempre que quieras repetirlo.",
    },
  },
  guide: {
    title: "Guía",
    not_a_page: "Ese enlace no lleva a una página de la guía",
    read_failed: "No se pudo leer esta página de la guía",
  },
  speech: {
    listen: "Escuchar",
    stop: "Detener la lectura en voz alta",
    browser_default: "Predeterminada del navegador",
  },
}
