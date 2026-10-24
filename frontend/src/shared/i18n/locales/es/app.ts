/** Words that belong to no one screen: sign-in, the language, the themes. */
import type { Messages } from "../en"

export const common: Messages["common"] = {
  back_to_workspace: "Volver al espacio de trabajo",
}

export const language: Messages["language"] = {
  label: "Idioma",
  browser: "El idioma del navegador",
  browser_hint: "El idioma que pida este navegador, o inglés",
}

export const auth: Messages["auth"] = {
  sign_in: "Iniciar sesión",
  email: "Correo electrónico",
  password: "Contraseña",
  email_required: "El correo electrónico es obligatorio",
  password_required: "La contraseña es obligatoria",
  checking_server: "Comprobando el servidor…",
  retry_connection: "Reintentar conexión",
  sign_in_failed: "No se pudo iniciar sesión. Comprueba el correo y la contraseña.",
  welcome_tagline: "Un solo lugar para todas las fuentes de datos con las que trabajas",
}

export const theme: Messages["theme"] = {
  label: "Tema",
  light: "Claro",
  paper_light: "Papel claro",
  paper_light_hint: "Papel claro cálido con un acento bronce",
  dark: "Oscuro",
  paper: "Papel oscuro",
  paper_hint: "Papel oscuro cálido con un acento bronce",
  midnight: "Medianoche",
  midnight_hint: "El más tenue: azul marino casi negro con un acento azul hielo",
  dark_blue: "Azul oscuro",
  dark_blue_hint: "Azul marino saturado con un acento cian",
  dark_purple: "Morado oscuro",
  dark_purple_hint: "Neón morado con acentos rosa y cian",
  system: "Sistema",
  system_hint: "Claro u Oscuro, según cambie el sistema operativo",
  switch_to: "Cambiar a {theme}",
}
