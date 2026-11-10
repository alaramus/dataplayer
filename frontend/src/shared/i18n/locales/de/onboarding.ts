/** Die Willkommenstour (features/onboarding) und die wenigen Worte des Fensters
    der Anleitung (features/guide) und des Vorlesens (features/speech). */
import type { Messages } from "../en"

export const onboarding: Messages["onboarding"] = {
  title: "Willkommen bei DataPlayer",
  intro: "Wählen Sie eine Sprache und das Aussehen der Anwendung.",
  tour_offer: "Danach eine Tour von drei Minuten: Sie legen eine kleine Datenbank an, arbeiten mit ihr und räumen sie wieder weg, mit einem Hinweis neben jeder Schaltfläche, die zu drücken ist.",
  position: "Schritt {n} von {total}",
  finish: "Fertig",
  next: "Weiter",
  take_tour: "Tour starten",
  look_around: "Selbst umsehen",
  mark_failed: "Die Tour konnte nicht als gesehen markiert werden",
  close_title: "Tour beenden?",
  close_message: "Die Tour öffnet sich nicht mehr von selbst. Sie können sie jederzeit in den Einstellungen unter „Touren“ machen.",
  close_confirm: "Tour beenden",
  keep_going: "Weitermachen",
  end_tour: "Tour beenden",
  more_tours: "Weitere Touren ansehen",
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
    service: {
      title: "Ein Server, hier gestartet",
      add: "Drücken Sie noch einmal +.",
      pick: "Wählen Sie Redis: Nichts bisher sah so aus.",
      start: "Diese Schaltfläche startet Redis gleich hier in Docker, mit Daten zum Ausprobieren, und legt die Verbindung für Sie an. Jeder Server dieses Katalogs mit einer solchen Schaltfläche startet genauso. Damit endet die Tour: Das Fenster gehört Ihnen.",
    },
  },
  tours: {
    basics: {
      title: "Die Grundlagen",
      summary: "Eine Datenbank anlegen, mit ihr arbeiten und sie wegräumen.",
    },
    practice_name: "practice",
    folder_name: "Meine Dateien",
    preparing: "Eine Übungsdatenbank für diese Tour wird angelegt…",
    setup_failed: "Die Tour konnte ihre Übungsdatenbank nicht vorbereiten",
    cleanup_failed: "Die Tour konnte ihre Übungsdatenbank nicht wegräumen",
    list: {
      take: "Starten",
      again: "Noch einmal",
    },
    views: {
      title: "Eine Tabelle, anders gelesen",
      summary: "Dieselbe Tabelle als Diagramm, als Struktur und als Dokumente.",
      back: "Gehen Sie zurück zum Tab {table}.",
      open: {
        title: "Die Übungstabelle öffnen",
        connection: "Diese Übungsdatenbank hat die Tour angelegt. Öffnen Sie sie.",
        table: "Öffnen Sie {table}.",
      },
      chart: {
        title: "Als Diagramm",
        hint: "Zeichnen Sie die Seite als Diagramm.",
      },
      structure: {
        title: "Als Struktur",
        hint: "Sehen Sie Spalten, Schlüssel und Indizes der Tabelle.",
      },
      document: {
        title: "Als Dokumente",
        hint: "Lesen Sie die Zeilen als Dokumente statt als Raster.",
      },
      closing: {
        title: "Fertig",
        text: "Die Übungsdatenbank wird entfernt, wenn Sie dies schließen.",
      },
    },
    pipeline: {
      title: "Eine Pipeline",
      summary: "Zeilen einer Tabelle als CSV-Datei in Ihrem Ordner gespeichert.",
      new: {
        title: "Eine neue Pipeline",
        space: "Öffnen Sie die Pipelines.",
        create: "Legen Sie eine neue Pipeline an.",
      },
      source: {
        title: "Woher die Zeilen kommen",
        connection: "Drücken Sie die Übungsdatenbank: Ihre Tabellen öffnen sich neben der Fläche.",
        schema: "Öffnen Sie main, das einzige Schema von SQLite.",
        tick: "Markieren Sie {table}.",
        done: "Legen Sie sie auf die Fläche.",
      },
      target: {
        title: "Wohin sie gehen",
        connection: "Drücken Sie jetzt Ihren Ordner.",
        top: "Markieren Sie den Ordner selbst.",
        done: "Legen Sie ihn auf die Fläche.",
      },
      link: {
        title: "Verbinden",
        hint: "Der Hinweis zeichnet jede mögliche Verbindung. Eine Zeile lässt sich auch auf eine andere ziehen.",
        press: "Drücken Sie die gestrichelte Verbindung von der Tabelle zum Ordner.",
      },
      run: {
        title: "Ausführen",
        hint: "Führen Sie die Pipeline aus. Die Verbindung speichert die Tabelle als CSV-Datei.",
        taken: "Im Ordner gibt es schon eine Datei dieses Namens: Wählen Sie unter „Wenn der Name vergeben ist“ „Beide behalten“ und führen Sie erneut aus.",
      },
      seen: {
        title: "Die Datei",
        space: "Gehen Sie zurück zu Daten.",
        folder: "Öffnen Sie Ihren Ordner.",
        file: "Hier ist die CSV, die die Pipeline gemacht hat. Die Übungsdatenbank geht am Ende, die Datei bleibt.",
      },
    },
    dashboards: {
      title: "Dashboards",
      summary: "Wo Dashboards entstehen und woher ihre Metriken kommen.",
      space: {
        title: "Dashboards",
        hint: "Öffnen Sie die Dashboards.",
      },
      new: {
        title: "Ein Dashboard",
        hint: "Hier beginnt ein Dashboard: Diagramme und Kacheln von Metriken auf einem Raster.",
        store: "Dashboards halten ihre Metriken in einem Speicher, den ein Administrator hier einmal startet.",
      },
      agent: {
        title: "Metriken von einem Agenten",
        open: "Öffnen Sie die Quellen der Metriken.",
        view: "Agenten melden die Maschinen, auf denen sie laufen.",
        register: "Registrieren Sie hier einen Agenten: Sie erhalten seinen Schlüssel und eine Docker-Compose-Datei, die ihn auf der zu beobachtenden Maschine startet.",
      },
      connections: {
        title: "Metriken Ihrer Verbindungen",
        view: "Auch Ihre Verbindungen können über sich berichten.",
        switch: "Wählen Sie eine Verbindung und schalten Sie sie ein: PostgreSQL, MySQL und Redis melden eigene Metriken.",
      },
    },
    agent: {
      title: "Der KI-Agent",
      summary: "Wo Schlüssel, Modell und Kontext des Agenten gewählt werden.",
      space: {
        title: "Der Agent",
        hint: "Öffnen Sie den KI-Bereich.",
      },
      chat: {
        title: "Ein Chat",
        hint: "Beginnen Sie einen neuen Chat.",
        close: "Schließen Sie die Einstellungen, um zu den Chats zurückzukehren.",
      },
      key: {
        title: "Sein Schlüssel",
        open: "Öffnen Sie die KI-Einstellungen.",
        hint: "Hier wird das Standardmodell gewählt, daneben die Schlüsselschaltfläche: Der Agent arbeitet mit Ihrem Schlüssel eines Anbieters, Anthropic, OpenAI und andere.",
      },
      model: {
        title: "Sein Modell",
        hint: "Wählen Sie das Modell des Chats.",
      },
      attach: {
        title: "Was er weiß",
        hint: "Hängen Sie eine Tabelle, einen Tab oder einen Knoten an: Der Agent liest, was Sie meinen, statt zu raten.",
      },
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
