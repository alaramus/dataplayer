# Docker

Ein Docker-Daemon auf einem anderen Rechner, erreicht über eine Ihrer
SSH-Verbindungen oder über TCP mit TLS. Sie sehen seine Container, Images, Volumes und Netzwerke,
was der Daemon über jedes sagt, Logs und Prozesse eines Containers und die
Berichte des Daemons selbst. Wie Verbindungen allgemein funktionieren, steht
auf der Seite [Verbindungen](connections.md).

## Was Sie sehen können

- Container, nach Compose-Projekt gruppiert, laufend oder nicht
- Images, Volumes und Netzwerke, und welche Container sie nutzen
- Was der Daemon über jedes davon sagt, als JSON-Baum
- Einen Container auf einen Blick, Geheimnisse bis zum Anzeigen verborgen
- Die Logs eines Containers, während sie entstehen, und seine Prozesse
- Die Schichten eines Images und die Anweisungen dahinter
- Die Engine: Versionen, Treiber, CPUs, Speicher, Platz, Ereignisse
- CPU, Speicher, Netzwerk und Datenträger laufender Container

## Was Sie ändern können

- Container starten, stoppen, neu starten, pausieren, Pause aufheben, beenden
- Die Container eines Compose-Projekts, alle auf einmal
- Container, Images, Volumes und Netzwerke entfernen
- Gestoppte Container und ungenutzte Images, Volumes, Netzwerke aufräumen
- Neue Volumes und Netzwerke
- Öffentliche Images ziehen, einen Container als Image festschreiben
- Eine Shell in einem laufenden Container, in einem Terminal
- Den Container einer Datenbank als eigene Verbindung öffnen

## Verbinden

**Transport** legt fest, wie der Daemon erreicht wird: **Socket über SSH**
oder **TCP mit TLS**, siehe unten. Für den Socket legen Sie zuerst eine
**SSH-Verbindung** zum Rechner an, auf dem der Daemon läuft; die Seite
**Verbindung** fragt dann nach:

- **SSH-Verbindung**: eine Ihrer SSH-Verbindungen. Ihr Konto muss den Socket
  des Daemons benutzen dürfen — auf den meisten Rechnern ist es dafür in der
  Gruppe `docker`;
- **Socket**: wo der Daemon auf diesem Rechner lauscht.
  `/var/run/docker.sock` für Docker, `/run/user/<uid>/docker.sock` für
  rootloses Docker. Die Karte **Podman** trägt `/run/podman/podman.sock` ein;
  ein rootloses Podman nutzt `/run/user/<uid>/podman/podman.sock`, und sein
  Socket muss eingeschaltet sein
  (`systemctl --user enable --now podman.socket`).

Der Socket wird über die SSH-Verbindung weitergeleitet, so wie eine Datenbank
über einen SSH-Tunnel erreicht wird; der SSH-Server muss das erlauben
(`AllowStreamLocalForwarding`, standardmäßig an). Sagt die Prüfung, der
Socket konnte nicht geöffnet werden, stimmt eines von drei Dingen nicht, und
OpenSSH sagt nicht welches: unter dem Pfad lauscht nichts, das Konto darf ihn
nicht benutzen, oder die Weiterleitung ist aus.

Der Daemon muss API 1.41 oder neuer sprechen (Docker 20.10 und später).

Der Docker-Daemon des Rechners, auf dem DataPlayer selbst läuft, wird nie
angeboten: Wer diesen Socket hat, hat den Rechner.

## Über TCP mit TLS

Ein Daemon, der auf TCP mit gegenseitigem TLS lauscht — `dockerd --tlsverify`,
meist auf Port 2376 —, wird ohne SSH erreicht. Das Formular fragt nach:

- **Host** und **Port**: der Host so, wie das Zertifikat des Daemons ihn nennt;
- **CA-Zertifikat**: `ca.pem`, die Stelle, die das des Daemons signiert hat;
- **Client-Zertifikat** und **Client-Schlüssel**: `cert.pem` und `key.pem`,
  die der Daemon akzeptiert. Der Schlüssel darf nicht verschlüsselt sein.

Fügen Sie jede Datei ganz ein, mit der Zeile `-----BEGIN`. **SSH-Tunnel**
bleibt auf **Direkt**, außer der Port ist nur aus einem anderen Netz
erreichbar; dann ist der Host der Name, unter dem der SSH-Server ihn erreicht.

Ein Daemon auf TCP ohne TLS — Port 2375 — wird abgelehnt, und die Prüfung sagt
es: Wer diesen Port erreicht, besitzt den Rechner. Die Prüfung sagt auch, was
fehlschlug: ein Zertifikat, das die CA nicht signiert hat, ein Host, für den
das Zertifikat nicht gilt, oder ein Client-Zertifikat, das der Daemon ablehnt.

## Der Katalog

- **System** enthält die Berichte des Daemons, siehe unten.
- **Container** enthält einen Ordner pro Compose-Projekt, benannt nach dem
  Label, das Compose schreibt, und **Ohne Projekt** für den Rest. Jeder
  Container zeigt seinen Zustand in einem Wort — läuft, gesund, ungesund,
  startet, pausiert, startet neu, gestoppt, fehlgeschlagen, erstellt oder
  tot — daneben den Status des Daemons, sein Image, seinen Compose-Dienst und
  seine veröffentlichten Ports.
- **Images** listet jedes Image nach seiner Id, mit oder ohne Tag, mit Größe
  und der Zahl der Container, die es nutzen.
- **Volumes** listet jedes Volume nach Namen; **Netzwerke** jedes Netzwerk,
  die drei von Docker zuerst, jedes als eingebaut, Compose oder eigenes
  markiert.
- Jeder dieser Ordner öffnet sich auch als Tabelle, nach jeder Spalte
  filter- und sortierbar. Mehr als zehntausend einer Art werden nicht
  aufgeführt.

## Wie sich ein Knoten öffnet

- **Untersuchen** eines Containers öffnet sich als **Überblick**: Zustand,
  Image, wann er erstellt und gestartet wurde oder wie er endete,
  Neustartrichtlinie und -zahl, Befehl, Health Check und seine letzten
  Ergebnisse, veröffentlichte Ports, Netzwerke mit Adressen, Mounts,
  Umgebung, Labels und Limits. Ein Hinweis sagt, wenn er mehr als dreimal
  neu startete oder wegen Speichermangels beendet wurde. Image, Volume,
  Netzwerk und Compose-Projekt sind Links, die sie im Katalog zeigen.
- **Als JSON** schaltet denselben Tab auf das, was der Daemon sagt, als
  JSON-Baum, und **Überblick** zurück.
- **Untersuchen** eines Images, Volumes oder Netzwerks öffnet sich ebenfalls
  als Überblick: beim Image Tags, Größe, Plattform, Befehl und Schichten (ein
  Link auf seinen **Verlauf**) mit den Containern, die es ausführen; beim
  Volume Treiber und Einhängepunkt mit den Containern, die es einhängen, und
  wo; beim Netzwerk Subnetze mit den Containern darin und ihren Adressen.
- Ein offener Überblick liest sich neu, wenn der Daemon eine Änderung an
  dem meldet, was er zeigt — ein Container gestartet, pausiert, mit einem
  Netzwerk verbunden oder gesund geworden —, solange ein Katalog dieser
  Verbindung offen ist.
- Eine Variable, deren Name PASSWORD, PASSWD, SECRET, TOKEN, KEY,
  CREDENTIAL oder PRIVATE enthält, erscheint als Punkte, bis Sie auf ihr
  Auge drücken, und wird erst dann kopiert. Das verbirgt sie vor einem
  Blick, nicht vor einem Leser: Das JSON zeigt sie offen, und jeder, mit dem
  Sie diese Verbindung teilen, sieht die Umgebung eines Containers.
- In einem Container: **Logs** — Zeit, Strom (stdout oder stderr) und Text
  jeder Zeile, Neuestes zuerst, bis zu zehntausend Zeilen zurück, eine Zeile
  bei 16 KB gekürzt — und **Prozesse**, was jetzt darin läuft. Ein gestoppter
  Container hat keine.
- In einem Image: **Verlauf**, seine Schichten.
- In einem Volume oder Netzwerk: **Container**, die es nutzen.

## Der Abschnitt System

- **Engine**: Versionen des Daemons, Betriebssystem, Kernel, Treiber, CPUs,
  Speicher und die Zahl der Container und Images, unter den Namen des
  Daemons. Registry-Spiegel und Proxys fehlen: Sie können Passwörter
  enthalten.
- **Speicherbelegung**: jedes Image, jeder Container, jedes Volume und jeder
  Build-Cache-Eintrag mit Größe, und ob Entfernen Platz freigäbe. Der Daemon
  misst dafür jedes Volume, das kann dauern.
- **Ereignisse**: was in der letzten Stunde geschah, Neuestes zuerst.

## Wenn etwas abgelehnt wird

- Lehnt die SSH-Verbindung oder der Socket ab, steht die ganze Verbindung,
  und jeder Bildschirm sagt warum.
- Ein Daemon hinter einem Autorisierungs-Plugin oder einem filternden Proxy
  kann eine Anfrage ablehnen: Das heißt dann **Der Docker-Server hat das nicht
  erlaubt**.

## Ändern

Wählen Sie einen Container, den Ordner eines Compose-Projekts oder einen
Knoten und öffnen Sie das Menü des Katalogs. Der Lebenszyklus eines Containers
braucht Schreibzugriff; Entfernen, Aufräumen, Ziehen, Festschreiben und neue
Volumes und Netzwerke brauchen Strukturzugriff.

- **Starten**, **Stoppen**, **Neu starten**, **Pausieren**, **Pause aufheben**
  und **Beenden (Signal)** wirken auf die gewählten Container oder auf alle
  Container eines gewählten Compose-Projekts. Jedes sagt zuerst, was es tut
  und welche Container schon so sind. Stoppen und Neu starten können einige
  Sekunden warten; Beenden sendet das gewählte Signal.
- **Container entfernen** lehnt einen laufenden ohne **Erzwingen** ab und
  kann seine anonymen Volumes mitnehmen. **Image entfernen** nennt die
  Container, die es nutzen; **Volume entfernen** lehnt ein eingebundenes ab;
  **Netzwerk entfernen** lehnt eines mit Containern ab, und Dockers eigene
  drei.
- In **Container**, **Images**, **Volumes** und **Netzwerke** listet das
  Aufräumen, was weggeht, bei Images auch den frei werdenden Platz. Der Daemon
  räumt auf, was beim Klick ungenutzt ist, also auch, was es inzwischen wurde.
- **Neues Volume** und **Neues Netzwerk** stehen in **Volumes** und
  **Netzwerke**.
- **Image ziehen** in **Images** und **Als Image festschreiben** an einem
  Container laufen als Aufträge unter **Aktivität**. Nur öffentliche Images
  lassen sich ziehen: Eine Registry mit Anmeldung wird nicht unterstützt.

## Ein Terminal im Container

Wählen Sie einen laufenden Container und im Menü des Katalogs **Terminal**.
Wählen Sie die Shell — `/bin/sh` gibt es in fast jedem Image, `/bin/bash` und
`/bin/ash` in manchen — und ob sie als root statt als Benutzer des Images
läuft. Sie öffnet sich unter **Terminals** am Fuß des Fensters, benannt nach
dem Container, und endet, wenn Sie sie schließen. Nur der Eigentümer der
Verbindung kann eines öffnen. Fehlt die gewählte Shell im Container, wird das
gesagt; öffnen Sie es erneut mit einer anderen.

## Logs und Ebenen, die mithalten

Solange die **Logs** eines Containers offen sind, erscheinen neue Zeilen, wie
der Container sie ausgibt, höchstens alle zwei Sekunden. Die Ebene des
Katalogs, auf der Sie stehen, liest sich neu, wenn der Daemon sie ändert: ein
Container stoppt, ein Image wird gezogen, ein Volume entfernt — durch
DataPlayer oder durch jemand anderen.

## Metriken auf einem Dashboard

Schalten Sie für die Verbindung die Erfassung ein und fügen Sie einem
Dashboard das Layout **Docker-Container** hinzu. Jede Abfrage misst bis zu
fünfzig laufende Container, nach Name: CPU — 100% ist eine voll ausgelastete
CPU, also kann es mehr als 100% werden —, Speicher ohne den Cache, den das
System zurücknehmen kann, Netzwerk- und Datenträgerverkehr pro Sekunde und die
Prozesse in jedem. Sie zählt auch laufende, pausierte und gestoppte Container;
**Nicht gemessene Container** zählt die laufenden über fünfzig. Eine Abfrage
dauert etwa eine Sekunde: Der Daemon misst jeden Container zweimal, um seine
CPU-Nutzung zu bestimmen.

## Suche

Die Suche im Katalog und die Suche über alles finden Container,
Compose-Projekte, Images nach jedem ihrer Tags, Volumes und Netzwerke nach
Name. In einem Ordner sucht sie nur in diesem Ordner.

## Der Container einer Datenbank als Verbindung

Wählen Sie einen Container von PostgreSQL, MySQL, MariaDB, Redis, MongoDB oder
ClickHouse und dann **Als Verbindung öffnen**. Ein Formular für eine neue
Verbindung öffnet sich, ausgefüllt aus dem Container:

- dieselbe SSH-Verbindung, als SSH-Tunnel;
- der veröffentlichte Port auf `127.0.0.1`, sonst die Adresse des Containers;
- Benutzer, Passwort und Datenbank, mit denen der Container gestartet wurde.

Prüfen und speichern Sie es. Ein Image wird an seinem Namen auf Docker Hub
erkannt, etwa `postgres` oder `mariadb`; eines aus einer anderen Registry
nicht. Das offizielle Redis-Image erhält sein Passwort auf der Befehlszeile,
also geben Sie es selbst ein. Nur der Eigentümer der Docker-Verbindung kann
das, denn das Formular trägt die Passwörter des Containers.

## Was Docker hier noch nicht hat

- Private Registries, und neue Container anlegen oder starten
