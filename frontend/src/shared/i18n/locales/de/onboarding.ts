/** Die Willkommenstour (features/onboarding) und die wenigen Worte des Fensters
    der Anleitung (features/guide) und des Vorlesens (features/speech). */
import type { Messages } from "../en"

export const onboarding: Messages["onboarding"] = {
  title: "Willkommen bei DataPlayer",
  intro: "Wählen Sie eine Sprache und das Aussehen der Anwendung.",
  tour_offer: "Danach eine Tour von drei Minuten: Sie legen eine kleine Datenbank an, arbeiten mit ihr und räumen sie wieder weg, mit einem Hinweis neben jeder Schaltfläche, die zu drücken ist.",
  position: "Schritt {n} von {total}",
  finish: "Fertig",
  take_tour: "Tour starten",
  look_around: "Selbst umsehen",
  mark_failed: "Die Tour konnte nicht als gesehen markiert werden",
  close_title: "Tour beenden?",
  close_message: "Die Tour öffnet sich nicht mehr von selbst. Sie können sie jederzeit in den Einstellungen unter „Willkommenstour“ machen.",
  close_confirm: "Tour beenden",
  keep_going: "Weitermachen",
  end_tour: "Tour beenden",
  tour: {
    make: {
      title: "Eine Datenbank anlegen",
      add: "Drücken Sie +, um eine Verbindung hinzuzufügen.",
      pick: "Wählen Sie SQLite.",
      here: "SQLite braucht keinen Server: Legen Sie die Datenbank gleich hier an, in Ihrem eigenen Speicher.",
      submit: "Behalten Sie das Angebotene, eine Datei mit Beispieldaten, und legen Sie sie an.",
    },
    open: {
      title: "Eine Tabelle öffnen",
      connection: "Öffnen Sie die neue Verbindung, um ihre Tabellen zu sehen.",
      table: "Öffnen Sie die Tabelle {table}.",
    },
    filter: {
      title: "Zeilen filtern",
      open: "Öffnen Sie die Filter.",
      fill: "Nur blockierte Aufgaben zeigen: Spalte status, gleich, blocked. Dann anwenden.",
    },
    edit: {
      title: "Einen Wert ändern",
      cell: "Doppelklicken Sie auf den Titel einer Aufgabe, um ihn zu ändern.",
      save: "Schreiben Sie einen neuen Titel und speichern Sie. Die Änderung geht direkt in die Datenbank.",
    },
    query: {
      title: "Eine Abfrage ausführen",
      open: "Öffnen Sie diese Tabelle als Abfrage: Die Konsole erhält ein passendes SELECT.",
      run: "Führen Sie es aus. Hier lässt sich beliebiges SQL schreiben.",
    },
    disconnect: {
      title: "Die Verbindung löschen",
      edit: "Öffnen Sie die Einstellungen der Verbindung.",
      delete: "Löschen Sie die Verbindung.",
      confirm: "Bestätigen Sie. Nur die Verbindung geht: Die Datenbankdatei bleibt in Ihrem Speicher.",
    },
    folder: {
      title: "Den eigenen Ordner verbinden",
      add: "Drücken Sie noch einmal +.",
      pick: "Wählen Sie „Dateien“.",
      create: "Legen Sie die Verbindung an.",
      save: "Der Pfad / ist Ihr ganzer persönlicher Speicher. Speichern Sie die Verbindung.",
    },
    find: {
      title: "Die Datei finden",
      connection: "Öffnen Sie die Ordnerverbindung.",
      folder: "Öffnen Sie {folder}: Dort liegt die angelegte Datenbank.",
    },
    remove: {
      title: "Die Datei löschen",
      tick: "Markieren Sie {file}.",
      actions: "Öffnen Sie das Aktionsmenü.",
      delete: "Wählen Sie „Löschen“.",
      confirm: "Bestätigen Sie. Von der Vorführung bleibt nichts, und die Ordnerverbindung gehört weiter Ihnen.",
    },
    finished: {
      title: "Die Grundlagen sitzen",
      text: "Verbindungen, Tabellen, Filter, Änderungen, Abfragen und Ihr eigener Speicher. Pipelines, Dashboards und der KI-Agent sind in der Leiste links. Die Tour finden Sie jederzeit wieder in den Einstellungen.",
    },
  },
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
