/** El recorrido de bienvenida (features/onboarding), y las pocas palabras de la
    ventana de la guía (features/guide) y de la lectura en voz alta (features/speech). */
import type { Messages } from "../en"

export const onboarding: Messages["onboarding"] = {
  title: "Te damos la bienvenida a DataPlayer",
  intro: "Elige un idioma y el aspecto de la aplicación, y luego haz un breve recorrido por lo que puede hacer, un clip silencioso por cada una de sus partes principales.",
  steps: {
    new_connection: "Crear una conexión nueva",
    tabs: "Trabajar con pestañas",
    table: "Trabajar con tablas",
    pipelines: "Trabajar con flujos",
    dashboards: "Trabajar con cuadros de mando",
    ai_agent: "Trabajar con el agente de IA",
  },
  position: "Paso {n} de {total}",
  start: "Iniciar el recorrido",
  finish: "Finalizar",
  next: "Siguiente",
  skip_tour: "Omitir el recorrido",
  skip: "Omitir",
  mark_failed: "No se pudo marcar el recorrido como visto",
  close_title: "¿Cerrar el recorrido de bienvenida?",
  close_message: "El recorrido no se volverá a abrir por sí solo. Puedes repetirlo en cualquier momento en Preferencias, en Recorrido de bienvenida.",
  close_confirm: "Cerrar el recorrido",
  keep_watching: "Seguir viendo",
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
