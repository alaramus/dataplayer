import type { Messages } from "../en"

export const preferences: Messages["preferences"] = {
  title: "Preferencias",
  saved: "Preferencia guardada",
  not_saved: "No se pudo guardar la preferencia",
  sections: {
    general: "General",
    general_summary: "Idioma, tema, voz de lectura y recorrido de bienvenida",
    connections: "Conexiones",
    connections_summary: "Con qué frecuencia se comprueban las conexiones mientras hay un espacio de trabajo abierto",
    ssh_keys: "Claves SSH",
    ssh_keys_summary: "Las claves que esta cuenta usa para las conexiones SSH",
  },
  language_summary:
    "El idioma de toda la interfaz. Se guarda con la cuenta, así que la acompaña a cualquier navegador; hasta que se elija uno, se usa el del navegador.",
  appearance: "Aspecto",
  appearance_summary:
    "Un tema claro u oscuro para toda la aplicación, o Claro y Oscuro según cómo cambie el sistema operativo. Se guarda con la cuenta, así que la acompaña a cualquier navegador.",
  voice: "Voz de lectura",
  voice_summary:
    "La voz que lee los mensajes en voz alta, allí donde se lean. Las voces son propias de este navegador. Se guarda en este navegador.",
  tour: "Recorrido de bienvenida",
  tour_summary:
    "Los breves clips de la primera visita, uno por cada parte principal de la aplicación. Se abre aquí de nuevo siempre que se quiera.",
  replay_tour: "Repetir el recorrido",
  checks: "Comprobar que las conexiones son accesibles",
  checks_summary:
    "Cada conexión se sondea según esta programación mientras hay un espacio de trabajo abierto, y el punto que la acompaña indica cuál fue la última respuesta. Un sondeo abre una conexión propia, así que conviene preguntar con menos frecuencia a un servidor lento o lejano.",
  checks_label: "Con qué frecuencia se comprueban las conexiones",
  interval: {
    off: "Nunca — solo cuando pulso comprobar",
    "15s": "Cada 15 segundos",
    "30s": "Cada 30 segundos",
    "1m": "Cada minuto",
    "5m": "Cada 5 minutos",
    "15m": "Cada 15 minutos",
  },
}
