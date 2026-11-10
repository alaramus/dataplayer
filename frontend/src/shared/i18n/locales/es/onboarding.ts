/** El recorrido de bienvenida (features/onboarding), y las pocas palabras de la
    ventana de la guía (features/guide) y de la lectura en voz alta (features/speech). */
import type { Messages } from "../en"

export const onboarding: Messages["onboarding"] = {
  title: "Te damos la bienvenida a DataPlayer",
  intro: "Elige un idioma y el aspecto de la aplicación.",
  tour_offer: "Después, haz un recorrido de tres minutos: crearás una pequeña base de datos, trabajarás con ella y la quitarás, con una pista junto a cada botón que hay que pulsar.",
  position: "Paso {n} de {total}",
  finish: "Terminar",
  next: "Siguiente",
  take_tour: "Hacer el recorrido",
  look_around: "Explorar por mi cuenta",
  mark_failed: "No se pudo marcar el recorrido como visto",
  close_title: "¿Terminar el recorrido?",
  close_message: "El recorrido no volverá a abrirse solo. Puedes hacerlo cuando quieras en Preferencias, en Recorridos.",
  close_confirm: "Terminar recorrido",
  keep_going: "Seguir",
  end_tour: "Terminar recorrido",
  more_tours: "Ver más recorridos",
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
    service: {
      title: "Un servidor, iniciado aquí",
      add: "Pulsa + una vez más.",
      pick: "Elige Redis: nada hasta ahora se le parecía.",
      start: "Este botón inicia Redis aquí mismo, en Docker, con datos para probarlo, y crea su conexión por ti. Cualquier servidor de este catálogo con un botón así se inicia igual. Aquí termina el recorrido: la ventana es tuya.",
    },
  },
  tours: {
    basics: {
      title: "Lo básico",
      summary: "Crear una base de datos, trabajar con ella y quitarla.",
    },
    practice_name: "practice",
    folder_name: "Mis archivos",
    preparing: "Creando una base de datos de práctica para este recorrido…",
    setup_failed: "El recorrido no pudo preparar su base de datos de práctica",
    cleanup_failed: "El recorrido no pudo quitar su base de datos de práctica",
    list: {
      take: "Hacer",
      again: "Otra vez",
    },
    views: {
      title: "Una tabla, leída de otras formas",
      summary: "La misma tabla como gráfico, como estructura y como documentos.",
      back: "Vuelve a la pestaña {table}.",
      open: {
        title: "Abre la tabla de práctica",
        connection: "El recorrido creó esta base de práctica. Ábrela.",
        table: "Abre {table}.",
      },
      chart: {
        title: "Como gráfico",
        hint: "Dibuja la página como un gráfico.",
      },
      structure: {
        title: "Como estructura",
        hint: "Mira las columnas, claves e índices de la tabla.",
      },
      document: {
        title: "Como documentos",
        hint: "Lee las filas como documentos en lugar de una cuadrícula.",
      },
      closing: {
        title: "Listo",
        text: "La base de práctica se quita al cerrar esto.",
      },
    },
    pipeline: {
      title: "Una canalización",
      summary: "Las filas de una tabla guardadas como archivo CSV en tu carpeta.",
      new: {
        title: "Una canalización nueva",
        space: "Abre las canalizaciones.",
        create: "Crea una canalización nueva.",
      },
      source: {
        title: "De dónde vienen las filas",
        connection: "Pulsa la base de práctica: sus tablas se abren junto al lienzo.",
        schema: "Abre main, el único esquema de SQLite.",
        tick: "Marca {table}.",
        done: "Ponla en el lienzo.",
      },
      target: {
        title: "Adónde van",
        connection: "Ahora pulsa tu carpeta.",
        top: "Marca la carpeta misma.",
        done: "Ponla en el lienzo.",
      },
      link: {
        title: "Únelas",
        hint: "La pista dibuja cada enlace posible. También se puede arrastrar una fila sobre otra.",
        press: "Pulsa el enlace discontinuo de la tabla a la carpeta.",
      },
      run: {
        title: "Ejecútala",
        hint: "Ejecuta la canalización. El enlace guarda la tabla como archivo CSV.",
        taken: "La carpeta ya tiene un archivo con ese nombre: en «Si el nombre ya está ocupado» elige «Conservar ambos» y vuelve a ejecutar.",
      },
      seen: {
        title: "El archivo",
        space: "Vuelve a Datos.",
        folder: "Abre tu carpeta.",
        file: "Aquí está el CSV que hizo la canalización. La base de práctica se va al terminar; el archivo se queda.",
      },
    },
    dashboards: {
      title: "Paneles",
      summary: "Dónde se crean los paneles y de dónde vienen sus métricas.",
      space: {
        title: "Paneles",
        hint: "Abre los paneles.",
      },
      new: {
        title: "Un panel",
        hint: "Aquí empieza un panel: gráficos y mosaicos de métricas en una cuadrícula.",
        store: "Los paneles guardan sus métricas en un almacén que un administrador inicia una vez, aquí.",
      },
      agent: {
        title: "Métricas de un agente",
        open: "Abre las fuentes de métricas.",
        view: "Los agentes informan de las máquinas donde se ejecutan.",
        register: "Registra aquí un agente: obtienes su clave y un archivo de Docker Compose que lo inicia en la máquina a vigilar.",
      },
      connections: {
        title: "Métricas de tus conexiones",
        view: "Tus conexiones también pueden informar de sí mismas.",
        switch: "Elige una conexión y actívala: PostgreSQL, MySQL y Redis envían sus propias métricas.",
      },
    },
    agent: {
      title: "El agente de IA",
      summary: "Dónde se eligen la clave, el modelo y el contexto del agente.",
      space: {
        title: "El agente",
        hint: "Abre el espacio de IA.",
      },
      chat: {
        title: "Un chat",
        hint: "Empieza un chat nuevo.",
        close: "Cierra los ajustes para volver a los chats.",
      },
      key: {
        title: "Su clave",
        open: "Abre los ajustes de IA.",
        hint: "Aquí se elige el modelo predeterminado y, a su lado, el botón de la clave: el agente trabaja con tu clave de un proveedor, Anthropic, OpenAI y otros.",
      },
      model: {
        title: "Su modelo",
        hint: "Elige el modelo que usa el chat.",
      },
      attach: {
        title: "Lo que sabe",
        hint: "Adjunta una tabla, una pestaña o un nodo: el agente lee a qué te refieres en lugar de adivinar.",
      },
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
