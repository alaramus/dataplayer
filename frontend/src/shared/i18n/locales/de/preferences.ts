import type { Messages } from "../en"

export const preferences: Messages["preferences"] = {
  title: "Einstellungen",
  saved: "Einstellung gespeichert",
  not_saved: "Die Einstellung konnte nicht gespeichert werden",
  sections: {
    general: "Allgemein",
    general_summary: "Sprache, Design und Lesestimme",
    connections: "Verbindungen",
    connections_summary: "Wie oft Verbindungen geprüft werden, solange ein Arbeitsbereich geöffnet ist",
    ssh_keys: "SSH-Schlüssel",
    ssh_keys_summary: "Die Schlüssel, die dieses Konto für SSH-Verbindungen verwendet",
    tours: "Touren",
    tours_summary: "Die Willkommenstour und kurze Touren durch jeden Teil, wann immer Sie möchten",
  },
  language_summary:
    "Die Sprache der gesamten Oberfläche. Sie wird im Konto gespeichert und folgt ihm in jeden Browser; bis eine gewählt ist, wird die des Browsers verwendet.",
  appearance: "Erscheinungsbild",
  appearance_summary:
    "Ein helles oder dunkles Design für die gesamte Anwendung oder Hell und Dunkel, während das Betriebssystem zwischen ihnen wechselt. Wird im Konto gespeichert und folgt ihm in jeden Browser.",
  voice: "Lesestimme",
  voice_summary:
    "Die Stimme, die Nachrichten überall vorliest, wo sie gelesen werden. Stimmen gehören diesem Browser. Wird in diesem Browser gespeichert.",
  storage: "Persönlicher Speicher",
  storage_summary: "Ihre eigenen Dateien auf diesem Server und das vom Administrator gesetzte Limit",
  storage_used: "{used} von {limit} belegt",
  storage_unlimited: "{used} belegt, kein Limit",
  checks: "Prüfen, ob Verbindungen erreichbar sind",
  checks_summary:
    "Jede Verbindung wird nach diesem Zeitplan geprüft, solange ein Arbeitsbereich geöffnet ist, und der Punkt daneben zeigt die letzte Antwort. Eine Prüfung öffnet eine eigene Verbindung, daher lohnt es sich, einen langsamen oder entfernten Server seltener abzufragen.",
  checks_label: "Wie oft Verbindungen geprüft werden",
  interval: {
    off: "Nie — nur wenn ich auf Prüfen drücke",
    "15s": "Alle 15 Sekunden",
    "30s": "Alle 30 Sekunden",
    "1m": "Jede Minute",
    "5m": "Alle 5 Minuten",
    "15m": "Alle 15 Minuten",
  },
}
