# Dashboards

Ein Dashboard zeichnet Metriken über die Zeit: Diagramme und Kacheln auf einem Raster. Metriken
kommen von Agenten, die Sie auf Ihren Rechnern betreiben, und von Verbindungen, die über sich
selbst berichten. Dashboards finden Sie im Bereich **Dashboards** des Schalters oben in der
linken Leiste.

## Vor dem ersten Dashboard

Metriken werden in einem eigenen Speicher gehalten, einer TimescaleDB-Datenbank. Ein
Administrator richtet ihn einmal für die gesamte Installation ein: Der Bereich Dashboards bietet
an, ihn hier zu starten oder einen vorhandenen anzubinden. Bis dahin wird allen anderen gesagt,
dass ein Administrator ihn einrichtet.

**Der Metrikspeicher** im Kopf der Leiste gehört dem Administrator: wo der Speicher liegt, wie viel
er belegt, wie lange er Daten behält und wie er entfernt wird. Einzelne Messwerte werden eine
Woche aufbewahrt; Mittelwerte über fünf Minuten und über eine Stunde länger.

## Woher die Metriken kommen

**Quellen** im Kopf der Leiste öffnet ein Fenster mit zwei Ansichten.

- **Agenten**: Ein Agent ist ein kleines Programm, das den Rechner meldet, auf dem es läuft, etwa
  seine Prozessoren, seinen Speicher und seine Prozesse. Geben Sie einen **Agentenname** ein und
  wählen Sie **Registrieren**: Das Fenster zeigt den Schlüssel des Agenten und eine Docker-Compose-Datei,
  die ihn mit diesem Schlüssel auf dem zu überwachenden Rechner startet. **Hosts** listet, was Ihre
  Agenten melden, mit System, Hardware, wie lange jeder schon läuft und wann er zuletzt gehört wurde.
  **Einen neuen Schlüssel ausstellen** schaltet den alten Schlüssel ab; das Entfernen eines Agenten verwirft von da an,
  was er sendet.
- **Verbindungen**: Eine PostgreSQL-, MySQL- oder Redis-Verbindung kann eigene Zähler melden. Ihr
  Besitzer schaltet **Meldungen** ein und wählt **Wie oft**, von alle 15 Sekunden bis alle 5 Minuten.
  Jeder, mit dem die Verbindung geteilt wird, kann zeichnen, was sie meldet.

Was ein Agent sendet, erscheint innerhalb weniger Sekunden in geöffneten Diagrammen.

## Ein Dashboard erstellen

1. **Neues Dashboard** im Kopf der Leiste. Es erhält einen Namen; benennen Sie es in seinem Kopf um.
2. **Widgets hinzufügen** öffnet die Quellen als Baum. Setzen Sie Häkchen bei den Reihen, die gezeichnet
   werden sollen, und klicken Sie auf **Hinzufügen**. Wenn Sie einen Host oder eine Verbindung auswählen,
   werden dessen fertige Layouts angeboten — **Linux-Host**, **PostgreSQL-Datenbank**, **MySQL-Server**,
   **Redis-Server** —, und **Layout hinzufügen** setzt eines unter die Widgets, die das Dashboard schon hat.
3. Ein Widget verschieben Sie am Kopf, in der Größe ändern Sie es an der Ecke, und einen Titel benennen
   Sie per Doppelklick um. Der Schlüssel `processes` eines Hosts erzeugt eine Tabelle seiner Prozesse,
   sortierbar nach CPU, Speicher oder PID.

Ein Dashboard wird kurz nach jeder Änderung gespeichert. **Bereich** wählt, wie weit zurück gezeichnet
wird — von den letzten 5 Minuten bis zu den letzten 30 Tagen —, und **Aktualisieren alle**, wie oft neu
gelesen wird.

Ein Widget kann das Dashboard füllen (**Das Dashboard mit diesem Widget füllen**) oder in einem Fenster
geöffnet werden, das bleibt, wenn Sie zu Data zurückwechseln.

## Ein Dashboard teilen

**Dieses Dashboard teilen** gibt einer Person Zugriff: **Kann ansehen** oder **Kann bearbeiten**. Sie finden es unter
**Mit Ihnen geteilt** in der Leiste. Wer Zugriff erhält, sieht jede Reihe des Dashboards, auch die Hosts
Ihrer Agenten, und sonst nichts von Ihren Daten. Wer nur ansehen darf, kann für sich einen anderen
Zeitraum wählen; nichts davon wird gespeichert.

Das Fenster enthält außerdem den Link des Dashboards. Er öffnet das Dashboard für jeden, dem Zugriff
gegeben wurde, und für niemanden sonst.

## Grenzen

- Das Löschen eines Dashboards entfernt seine Widgets; die Metriken bleiben.
- Ein Host, der immer wieder neu startet, steht unter **Braucht dich** in der Aktivitätsglocke.
