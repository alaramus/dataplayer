/** Die Willkommenstour (features/onboarding) und die wenigen Worte des Fensters
    der Anleitung (features/guide) und des Vorlesens (features/speech). */
import type { Messages } from "../en"

export const onboarding: Messages["onboarding"] = {
  title: "Willkommen bei DataPlayer",
  intro: "Wählen Sie eine Sprache und das Aussehen der Anwendung und machen Sie dann eine kurze Tour durch das, was sie kann — einen stillen Clip für jeden ihrer Hauptteile.",
  steps: {
    new_connection: "Eine neue Verbindung erstellen",
    tabs: "Mit Tabs arbeiten",
    table: "Mit Tabellen arbeiten",
    pipelines: "Mit Pipelines arbeiten",
    dashboards: "Mit Dashboards arbeiten",
    ai_agent: "Mit dem KI-Agenten arbeiten",
  },
  position: "Schritt {n} von {total}",
  start: "Tour starten",
  finish: "Fertig",
  next: "Weiter",
  skip_tour: "Tour überspringen",
  skip: "Überspringen",
  mark_failed: "Die Tour konnte nicht als gesehen markiert werden",
  close_title: "Willkommenstour schließen?",
  close_message: "Die Tour öffnet sich nicht mehr von selbst. Sie können sie jederzeit in den Einstellungen unter „Willkommenstour“ erneut abspielen.",
  close_confirm: "Tour schließen",
  keep_watching: "Weiterschauen",
  guide: {
    title: "Anleitung",
    not_a_page: "Dieser Link führt nicht zu einer Seite der Anleitung",
    read_failed: "Diese Seite der Anleitung konnte nicht gelesen werden",
  },
  speech: {
    listen: "Anhören",
    stop: "Vorlesen beenden",
    browser_default: "Browser-Standard",
  },
}
