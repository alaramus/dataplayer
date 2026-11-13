# Dienste und Terminals

DataPlayer kann für Sie Datenbankserver und andere Quellen auf dem Rechner starten, auf dem es läuft,
und Terminals zu Ihren Verbindungen öffnen. Beides lebt im Feld am Fuß des Bildschirms, geöffnet über
seine Werkzeuge auf der unteren linken Leiste.

## Einen Server hier starten

Wo diese Installation Container ausführen darf, bietet das Feld einer Quellenart unter **Neue Verbindung**
**… hier starten** an — PostgreSQL, MySQL, Redis, einen SSH-Server und andere. Wie gefragt wird und was Sie
bekommen, steht auf der Seite [Verbindungen](connections.md). Der Server läuft in Docker auf diesem
Rechner, und seine Verbindung wird für Sie angelegt.

Eine ausgegraute Schaltfläche sagt beim Darauf-Zeigen, warum: Diese Installation darf gar keine Container
ausführen oder nicht diese Art.

## Das Werkzeug Services

**Dienste** listet die hier für Sie gestarteten Server auf, mit dem Zustand jedes Servers und seines
Containers.

- **Stoppen** stoppt einen Server; was darin gespeichert ist, bleibt erhalten. **Starten** startet ihn
  wieder.
- **Von vorn beginnen** entfernt einen Server, der nicht gestartet ist, und seine Daten, und versucht es erneut.
- **Wo er erreichbar ist** zeigt Host, Port, Benutzer und Datenbank, um von Ihren eigenen Werkzeugen aus
  zuzugreifen, und eine Verbindungszeichenfolge. Sein Passwort wird nur einmal angezeigt, wenn der Server
  angelegt wird, es sei denn, Sie haben ein eigenes eingetippt.
- **Was er ausgegeben hat** zeigt die eigene Ausgabe des Servers.
- **Diesen Dienst entfernen** entfernt den Server und alles, was in ihm gespeichert ist.
  **Auch die Verbindung entfernen** entfernt auch seine Verbindung.

Starten, Stoppen und Entfernen laufen im Hintergrund; die Aktivitätsglocke zeigt, wie sie vorankommen.

## Terminals

**Terminals** öffnet ein Terminal zu einer Ihrer Verbindungen:

- bei einer SSH-Verbindung eine Shell auf diesem Server;
- bei einer Datenbankverbindung, die es anbietet, deren eigenes Client-Programm — `psql`, `mysql`, `cqlsh`,
  `zkCli`, die Werkzeuge von Kafka, `rabbitmqadmin` und andere — angemeldet als diese Verbindung. Es läuft in
  einem Container, den dieser Server startet, und wird deshalb nur dort angeboten, wo Container erlaubt sind.
  Die Seite jeder Quellenart sagt, was sie öffnet.

Mehrere Terminals können gleichzeitig offen sein, jedes in einem Tab des Felds. Ein Terminal behält jede
Taste für sich, Ctrl+K eingeschlossen. Das Schließen seines Tabs beendet es.

Terminals werden nur zu Verbindungen geöffnet, die Ihnen gehören.

## Sicherungen

Eine Datenbank, die sich herauskopieren lässt, hat **Sicherungen** im Aktionsmenü ihres Katalogs:
**Diese Datenbank sichern** erstellt eine Sicherung, eine Datei in Ihrem eigenen Speicher; **Wiederherstellen**
schreibt sie zurück und ersetzt, was dort liegt; Löschen entfernt die Datei. Die Seite jeder Quellenart sagt,
ob sie Sicherungen unterstützt.

## Logs

**Protokolle** auf der unteren linken Leiste eines Administrators liest das eigene Protokoll des Servers: gefiltert
nach Stufe und Prozess, durchsucht nach Text oder nach dem Verweis, den eine Fehlermeldung nennt, und
verfolgt, während es wächst.
