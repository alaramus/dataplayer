# Suche

Eine Suche findet alles, was Sie in DataPlayer sehen: Verbindungen und was in ihnen steckt — Tabellen,
Dateien, Schlüssel, Topics —, und was die Anwendung für Sie aufbewahrt: gespeicherte Abfragen, Pipelines,
Dashboards, Chats, Dienste, SSH-Schlüssel, offene Tabs und Tab-Gruppen, Quellenarten und Seiten dieses
Handbuchs.

## Das Suchfeld

Das Feld in der Kopfzeile, **Alles durchsuchen**, öffnet die Suche. Ctrl+K (⌘K auf dem Mac) tut dasselbe
von überall außer einem Terminal.

- Ergebnisse erscheinen während des Tippens, gruppiert: offene Tabs, Verbindungen, eine Gruppe je
  Verbindung, Favoriten, Pipelines, Dashboards, Unterhaltungen, Dienste, SSH-Schlüssel, das Handbuch,
  Quellenarten. **Beste Treffer** stehen zuerst.
- Ein Name passt, wenn er jedes eingegebene Wort enthält, in beliebiger Reihenfolge und ohne Beachtung
  der Groß- und Kleinschreibung. Ein genauer Name oder einer, der mit Ihrem ersten Wort beginnt, steht
  über einem, der die Wörter nur enthält.
- Während des Tippens werden langsame Stellen nicht gefragt. **Enter** sucht überall und wartet auf jede
  Verbindung so lange, wie es nötig ist.
- Jede Stelle sagt, was mit ihr geschehen ist: nichts gefunden, nicht rechtzeitig geantwortet, nicht
  erreichbar, ausgeschaltet, gesperrt. Manche bieten eine Geste an — **Erneut versuchen**, **Trotzdem suchen**,
  **Den SSH-Schlüssel entsperren**.
- **Den Agenten fragen** am Ende der Liste öffnet einen neuen Chat mit Ihren Worten darin, noch nicht gesendet.
- Ein leeres Feld zeigt die letzten Suchen und das, was Sie kürzlich geöffnet haben.

Ein Klick auf ein Ergebnis öffnet es dort, wo es liegt: eine Tabelle im Arbeitsbereich, eine Pipeline in
Pipelines, ein Chat im Bereich AI, eine Seite des Handbuchs im Fenster des Handbuchs. **Im Katalog anzeigen**
findet stattdessen eine Tabelle oder Datei in ihrem Katalog.

## Eine Verbindung durchsuchen

Wird die Suche geöffnet, während ein Katalog den Fokus hat, bietet sie zuerst **In ‹Verbindung› suchen**
an: Der Rechtspfeil übernimmt es, Backspace entfernt es. Das Filterfeld des Katalogs tut dasselbe für eine
Ebene, seine Suchschaltfläche für alles darunter.

## Der Tab Search

**Alle Ergebnisse anzeigen** oder Enter öffnet den Tab **Suche** in der Arbeitsspalte. Er enthält die ganze
Antwort und filtert sie nach Gruppe, Verbindung, Art und dem Datum einer Änderung.

**In Dateien suchen** liest den Text jeder Datei unterhalb der angehakten Verbindungen. Das kann Minuten
dauern, überspringt Binärdateien und Dateien über 8 MB (1 MB über SSH) und läuft im Hintergrund; was
gefunden wird, erscheint laufend, und **Stoppen** behält das bis dahin Gefundene.

## Der Suchindex

Eine Verbindung mit vielen Namen antwortet langsam, wenn sie jedes Mal gefragt wird. Ihr Besitzer kann
stattdessen eine Liste ihrer Namen auf diesem Server führen: **Suchindex…** im Aktionsmenü des
Katalogs, das Werkzeug **Suchindex** auf der linken unteren Leiste oder die Seite **Optionen** des
Verbindungsfensters.

- **Eine Liste von Namen für die Suche behalten** kopiert die Namen von Tabellen, Schlüsseln, Ordnern und Dateien als
  Klartext in die Datenbank dieses Servers, gelesen mit den Zugangsdaten des Besitzers. Ausschalten löscht
  die Kopie.
- **Erneut lesen innerhalb von** — 1 Stunde, 6 Stunden, 1 Tag oder 1 Woche — legt fest, wie alt die Liste werden
  darf, bevor die Suche die Quelle fragt. **Jetzt lesen** liest sie sofort.
- **Inhalt der Dateien** hält für einen Ordner auch den Text der Dateien darunter, sodass ein Wort darin bei
  Enter gefunden wird, ohne sie erneut zu öffnen.
- Nur der Besitzer schaltet es ein; eine Person, mit der die Verbindung geteilt wird, sieht den Zustand.

Läuft auf diesem Server das Modell dafür, wird eine gespeicherte Liste auch nach Bedeutung durchsucht: Bei
Enter fügen Zeilen mit der Markierung **Nach Bedeutung** hinzu, was die Wörter allein übersehen haben.
