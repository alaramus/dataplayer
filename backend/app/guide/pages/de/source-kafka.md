# Kafka

Ein Kafka-Cluster. Sie sehen seine Topics und Consumer-Gruppen, lesen die
Nachrichten eines Topics als Zeilen und sehen, wie weit jede Gruppe
zurückliegt. Wie Verbindungen allgemein funktionieren, steht auf der Seite
[Verbindungen](connections.md).

## Was Sie sehen können

- Topics, Consumer-Gruppen und, getrennt davon, Kafkas eigene Topics
- Nachrichten eines Topics als Zeilen, die neuesten zuerst, ab Zeit oder Offset
- Die Felder von JSON-Nachrichten, jedes in einer eigenen Spalte
- Jede Partition eines Topics: Leader, Replikate und Offsets
- Die Einstellungen, die an einem Topic gesetzt sind
- Wo jede Consumer-Gruppe in jeder Partition steht, und ihr Rückstand
- Berichte des Clusters: Broker, Einstellungen, Partitionen mit Handlungsbedarf
- Rückstand, Nachrichten pro Sekunde und Zustand des Clusters auf einem Dashboard
- Topics und Gruppen per Namenssuche
- Die Nachrichten eines Topics als Datei heruntergeladen
- Kafkas eigene Werkzeuge, für die Verbindung eingerichtet, in einem Terminal

## Was Sie ändern können

- Nachrichten senden, einzeln oder als eingefügte Zeilen
- Neue Topics mit ihren Partitionen und Einstellungen
- Topics löschen, ihre Einstellungen ändern, Partitionen hinzufügen
- Die Nachrichten eines Topics löschen, alle oder die vor einem Zeitpunkt
- Positionen einer Gruppe an Anfang, Ende oder einen Zeitpunkt verschieben
- Consumer-Gruppen löschen
- Alles, was Kafkas Werkzeuge ändern können, im Terminal

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach:

- **Broker**: `host:port` eines oder mehrerer Broker, durch Kommas getrennt.
  Einer genügt: Er sagt DataPlayer, wo die anderen sind;
- **TLS**: eine verschlüsselte Verbindung, bei der die Zertifikate der Broker
  geprüft werden;
- **CA-Zertifikat**: die Stelle, die sie signiert hat, als PEM, wenn das
  System ihr nicht schon vertraut;
- **Authentifizierung**: **Keine** oder ein Benutzer mit Passwort über
  **SASL PLAIN**, **SASL SCRAM-SHA-256** oder **SASL SCRAM-SHA-512**.

DataPlayer verbindet sich mit den Adressen, die die Broker über sich selbst
angeben; sie müssen vom DataPlayer-Server unter diesen Namen erreichbar sein.
Ein SSH-Tunnel wird nicht unterstützt.

## Der Katalog

- **Topics**, **Consumer-Gruppen** und **Interne Topics** — Kafkas eigene wie
  `__consumer_offsets`, deren Namen mit einem Unterstrich beginnen.
- Ein Topic zeigt, wie viele Partitionen es hat und wie viele Nachrichten sie
  umfassen. Die Zahl ist eine Obergrenze: Kompaktierte Topics haben Lücken.
- Eine Gruppe zeigt, ob sie stabil ist, neu verteilt wird oder keine Consumer
  hat, und wie viele Consumer sie hat.
- Eine Ebene zeigt die ersten tausend nach Namen.

## Die Nachrichten eines Topics

- Eine Zeile pro Nachricht: Partition, Offset, Zeit, Schlüssel, Wert und Header.
- Sind die Werte JSON-Objekte, ist jedes Feld auch eine Spalte, benannt mit
  `value.` und dem Feldnamen. Die Felder stammen aus den neuesten zweihundert
  Nachrichten.
- Ein Schlüssel oder Wert, der kein Text ist, wird hexadezimal gezeigt.
- Die neuesten zuerst, über alle Partitionen. Sortieren Sie nach **timestamp**,
  um bei den ältesten zu beginnen; keine andere Spalte sortiert.
- Filter auf **partition**, **offset** oder **timestamp** bestimmen, wo das
  Lesen beginnt und endet: Kafka findet diese Stelle selbst, wie lang das Topic
  auch ist.
- Filter auf Schlüssel, Wert, Header und Felder durchsuchen die gelesenen
  Nachrichten, bis zu hunderttausend pro Seite.
- Eine Seite reicht höchstens zehntausend Nachrichten vom Ende zurück. Um
  weiter zurückzuschauen, filtern Sie nach Zeit oder nach Partition und Offset.
- Das Lesen eines Topics tritt keiner Consumer-Gruppe bei und verschiebt keine
  Position.

## Nachrichten senden

- **+** über den Zeilen eines Topics fügt eine Nachricht hinzu. Füllen Sie aus,
  was Sie brauchen: Alles darf leer bleiben.
- Ist **partition** leer, wählt Kafka nach Schlüssel; ist **timestamp** leer,
  gilt jetzt.
- **key** und **value** sind Text; `0x` gefolgt von Hex-Ziffern wird als diese
  Bytes gesendet.
- Lassen Sie **value** leer und füllen Sie die `value.`-Felder, um ein
  JSON-Objekt daraus zu senden.
- **headers** ist ein JSON-Objekt aus Text, etwa `{"source": "manual"}`.
- In ein Topic eingefügte Zeilen werden als Nachrichten gesendet. Lässt sich
  ein Wert nicht lesen, wird nichts gesendet und die Zelle genannt.
- In Kafkas eigene Topics wird von hier nicht geschrieben.

## Eine Consumer-Gruppe

- Eine Zeile pro Partition, die die Gruppe liest: Topic, Partition, die von der
  Gruppe festgeschriebene Position, das Ende der Partition und der Rückstand
  dazwischen, mit dem Consumer, der sie liest. Die Zeilen werden alle zehn
  Sekunden aktualisiert.

## Das Detailfenster

Wählen Sie ein Topic oder eine Gruppe und dann **Details** im Menü des Katalogs.

- Ein Topic: Anzahl der Nachrichten, eine Zeile pro Partition mit Leader,
  Replikaten, synchronen Replikaten und Offsets, und die am Topic gesetzten
  Einstellungen.
- Eine Gruppe: Zustand, Consumer, gesamter Rückstand, Koordinator-Broker,
  Zuweisungsstrategie und Topics.

## Kafkas Werkzeuge

**Terminal** bei einer Kafka-Verbindung öffnet Kafkas eigene
Kommandozeilenwerkzeuge, die seine Dokumentation verwendet, bereits auf die
Verbindung gerichtet: ihre Broker, ihr TLS und ihren Benutzer. Geben Sie ein
Werkzeug ohne `--bootstrap-server` ein:

- `kafka-topics.sh --list` — die Topics
- `kafka-console-consumer.sh --topic NAME --from-beginning` — ein Topic lesen;
  Strg+C beendet es
- `kafka-consumer-groups.sh --describe --all-groups` — der Rückstand jeder Gruppe

Geben Sie `--bootstrap-server` selbst an, um ein Werkzeug auf einen anderen
Cluster zu richten. Das Terminal läuft in einem Container auf dem
DataPlayer-Server; dieser Server muss also Container starten dürfen, und die
Broker müssen von dort erreichbar sein.

## Topics und Gruppen ändern

Markieren Sie ein Topic auf der Ebene **Topics** und öffnen Sie das Menü des
Katalogs:

- **Neues Topic** — ein Name, die Anzahl der Partitionen, ein
  Replikationsfaktor (leer für den Standard des Brokers) und Einstellungen, ein
  `name=value` pro Zeile.
- **Topic löschen** — das Fenster sagt, wie viele Nachrichten verschwinden und
  welche Gruppen das Topic lesen.
- **Einstellungen ändern** — öffnet mit den eigenen Einstellungen des Topics;
  entfernen Sie eine Zeile, um die Einstellung auf den Standard des Brokers
  zurückzusetzen.
- **Partitionen hinzufügen** — Partitionen lassen sich nur hinzufügen, nie
  entfernen. Ein Schlüssel kann danach in einer anderen Partition landen.
- **Nachrichten löschen** — alle oder die vor einem Zeitpunkt. Das lässt sich
  nicht rückgängig machen.

Markieren Sie eine Gruppe auf der Ebene **Consumer-Gruppen** für **Positionen
verschieben**: an den Anfang, das Ende oder einen Zeitpunkt, für alle ihre
Topics oder eines. Die Positionen einer Gruppe werden nur verschoben, solange
keiner ihrer Consumer läuft. Das Fenster zeigt jede Partition vorher und
nachher. **Gruppe löschen** entfernt eine Gruppe mit ihren Positionen, ebenfalls
nur, solange niemand in ihr liest.

## Der Bereich Cluster

Oben im Katalog sammelt **Cluster**, was der Cluster über sich sagt:
**Cluster** (ID, Controller und wie viele Broker, Topics und Partitionen),
**Broker**, **Broker-Einstellungen** (die von Kafkas Standard abweichenden) und
**Partitionen mit Handlungsbedarf** (leer, wenn alles in Ordnung ist). Der erste
und der letzte Bericht werden alle zehn Sekunden aktualisiert.

## Dashboards, Suche und Downloads

- Das Dashboard **Kafka-Cluster** zeichnet den Rückstand jeder Gruppe, die
  Nachrichten pro Sekunde jedes Topics und die Partitionen mit
  Handlungsbedarf, für die ersten hundert Topics und Gruppen nach Namen.
- Die Suche in der Kopfzeile findet Topics und Gruppen nach Namen.
- **Herunterladen** bei einem Topic speichert die Nachrichten, die seine Seite
  zeigen würde, mit ihren Filtern und ihrer Reihenfolge, bis zu zehntausend vom
  Ende jeder Partition. Eine Gruppe lädt jede Position herunter.

## Ein Topic in einer Pipeline

Ein Topic kann mitten in einer Pipeline stehen: eine Verknüpfung schreibt
hinein, andere tragen das Angekommene in Tabellen.

- **Zeilen hinzufügen** in ein Topic sendet die Zeilen als Nachrichten.
- **Neue Nachrichten zu einer Tabelle hinzufügen** liest nur, was seit dem
  letzten Lauf dieser Verknüpfung angekommen ist. Es ist der einzige Weg aus
  einem Topic in einer Pipeline: das ganze Topic bei jedem Lauf erneut zu
  lesen, würde dieselben Zeilen wieder hinzufügen.
- Jede solche Verknüpfung liest als eigene Consumer-Gruppe namens
  `dataplayer-link-` und der ID der Verknüpfung, im Bereich der Verknüpfung
  angezeigt. Ihr Rückstand steht auf der Ebene **Consumer-Gruppen**.
- **Der erste Lauf liest** wählt, wo der erste Lauf beginnt: am Anfang des
  Topics oder nur bei Nachrichten, die danach kommen. Hat die Gruppe eine
  Position, ändert die Wahl nichts; um erneut zu lesen, verschieben Sie die
  Positionen der Gruppe.
- Jeder Block Zeilen wird zuerst geschrieben und seine Position danach
  gespeichert. Scheitert ein Lauf dazwischen, schreibt der nächste den Block
  erneut: keine Nachricht geht verloren, selten kommt eine doppelt an.
- **Neue Nachrichten zu einer neuen Tabelle hinzufügen**, zu einem Schema statt
  zu einer Tabelle gezogen, legt die Tabelle beim ersten Lauf an — Name,
  Spalten und Typen im Fenster gewählt — und fügt danach hinzu. Gehören
  partition und offset des Topics zu ihren Spalten, bekommt sie dort einen
  Schlüssel darauf, wo die Datenbank es erlaubt (PostgreSQL, MySQL, MariaDB,
  SQLite), und eine doppelt geschriebene Nachricht wird einmal gespeichert.
  Eine später entfernte Tabelle wird nicht neu angelegt: verschieben Sie die
  Positionen der Gruppe an den Anfang, um alles in eine neue zu lesen.
- **Das Neueste je Schlüssel behalten**, zu einer Redis-Datenbank oder einem
  Ordner gezogen, hält den neuesten Wert jedes Nachrichtenschlüssels als
  eigenen Schlüssel, auf Wunsch mit Lebensdauer; siehe die Redis-Seite.
- Solange die Pipeline eingeschaltet ist, überträgt eine Verknüpfung, die ein
  Topic liest, Angekommenes binnen Sekunden statt beim nächsten Lauf; **Solange
  die Pipeline eingeschaltet ist** in ihrem Feld stellt sie stattdessen auf den
  Zeitplan. Die Pipeline schaut alle paar Sekunden nach, läuft nach einem
  Neustart des Servers weiter, und einmaliges Ausführen lässt eine solche
  Verknüpfung solange aus. Eine fehlschlagende Verknüpfung wird etwas später
  erneut versucht, die übrigen laufen weiter.
- Nachrichten, die Kafka gelöscht hat, bevor die Verknüpfung sie las, werden
  im Ergebnis des Laufs gezählt.
- Kafka vergisst die Positionen einer Gruppe nach einer Woche ohne
  Schreiben; eine seltener laufende Verknüpfung beginnt dann neu, wie
  **Der erste Lauf liest** es sagt.

## Ein eigenes Kafka

Unter **Dienste** lässt sich ein Kafka-Broker auf diesem Rechner starten, wenn
dieser Server Container ausführen darf. Er fragt nach keinem Passwort — ein
Broker antwortet jedem, der ihn erreicht — und ist nur von diesem Rechner
erreichbar. Seine Verbindung wird für Sie angelegt.

Fordern Sie Beispieldaten an, um ein Lab zu erhalten:

- `lab.orders` — dreihundert JSON-Bestellungen eines Tages in drei Partitionen,
  nach Kunde verschlüsselt;
- `lab.prices` — der letzte Preis pro Symbol, ein kompaktiertes Topic;
- `lab.events` — Textzeilen mit Headern;
- `lab.sensor` — als Bytes gespeicherte Messwerte, hexadezimal gezeigt;
- die Gruppe `lab-billing`, die `lab.orders` teilweise gelesen hat, damit ihr
  Rückstand zu sehen ist.

Ein Broker sagt seinen Clients, wo er ist, und dieser nennt die Adresse, die er
innerhalb von DataPlayer hat. Katalog, Terminal und Pipelines erreichen ihn
dort; ein Werkzeug auf Ihrem eigenen Rechner nur über das Terminal.

## Was Kafka hier noch nicht hat

Topics in eine andere Verbindung kopieren und Backups werden nicht angeboten.
Kafka kopiert mit MirrorMaker, einem Dienst, der weiterläuft, und sein Backup
sind die Logdateien der Broker; jede Nachricht erneut zu senden, verspräche
keines von beiden.
