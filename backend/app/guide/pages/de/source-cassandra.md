# Cassandra

Ein Cluster von Apache Cassandra oder ScyllaDB, erreicht über CQL. Sie
durchsuchen seine Keyspaces, lesen Tabellen und materialisierte Sichten
seitenweise, sehen, wie der Schlüssel einer Tabelle aufgebaut ist, und lesen
ihr DDL so, wie der Server es schreibt. Beide Produkte sind eine Art von
Verbindung: Der Katalog der Typen zeigt für jedes eine Karte, und die
Verbindung sagt, welches sie erreicht hat.
Wie Verbindungen allgemein funktionieren, steht auf der Seite
[Verbindungen](connections.md).

## Was Sie sehen können

- Keyspaces, Tabellen und materialisierte Sichten
- Zeilen seitenweise, vom Server gefiltert, Werte genau wie gespeichert
- Partitionsschlüssel, Clustering-Spalten und Sekundärindizes einer Tabelle
- Das DDL einer Relation, wie der Server es schreibt
- Die virtuellen Tabellen von Cassandra, etwa `system_views`
- Die Ergebnisse Ihres CQL, in der Konsole oder in cqlsh
- Knoten, Clients, Tabellengrößen, Einstellungen und Rollen des Clusters
- Alle passenden Zeilen, als Datei heruntergeladen
- Clients, Anfragen und Größe des Knotens auf einem Dashboard

## Was Sie ändern können

- Tabellendaten: Zellen bearbeiten, Blöcke einfügen, Zeilen anlegen und löschen
- Spalten und Sekundärindizes einer Tabelle
- Neue Tabellen mit Partitions- und Clustering-Schlüssel aus dem Designer
- Keyspaces anlegen und entfernen; Tabellen leeren und entfernen
- Tabellen samt Struktur in eine andere Cassandra-Verbindung kopiert
- Daten und Struktur per CQL in der Konsole, eine Änderung nach der anderen

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach:

- **Host** und **Port** des nativen Protokolls, 9042, sofern der Server nichts
  anderes vorgibt;
- **TLS**, mit dem Zertifikat des Servers gegen den Host geprüft;
- **Authentifizierung**: Benutzer und Passwort, oder nichts für einen Server,
  der keines prüft. Ein neuer Cassandra- oder ScyllaDB-Server hat oft
  `cassandra` mit dem Passwort `cassandra`;
- **Keyspace**: wo sich der Katalog öffnet. Er darf leer bleiben;
- **Konsistenz**: wie viele Replikate einen Lesevorgang beantworten und einen
  Schreibvorgang bestätigen. `LOCAL_ONE`, sofern Sie nichts anderes wählen.

Eine Verbindungszeichenfolge wie `cassandra://ann@db.example.com:9042/shop`,
in **URL** eingefügt, füllt diese Felder; `scylla://` wird ebenfalls gelesen,
`?ssl=true` schaltet TLS ein und `?consistency=LOCAL_QUORUM` wählt die Stufe.

Jede Anweisung geht an den Knoten, den Sie nennen, auch wenn der Cluster
weitere hat: Die Adressen, die Knoten von sich angeben, sind von hier oft nicht
erreichbar — hinter Docker, einem NAT oder einem SSH-Tunnel —, der genannte
Knoten schon. Er fragt die anderen nach dem, was er nicht hält.

Unterstützt werden Cassandra 4.0 und ScyllaDB 5.4 und neuer. Ein älterer
Server wird beim Prüfen der Verbindung mit seiner Version abgelehnt.

## Der Katalog

- Die erste Ebene sind Keyspaces. Der der Verbindung kommt zuerst; `system`
  und die `system_…`-Keyspaces gehören dem Server und sind so markiert, ebenso
  `audit` von ScyllaDB.
- In einem Keyspace liegen seine Tabellen und materialisierten Sichten.
  ScyllaDB hält einen Sekundärindex in einer verborgenen Sicht; sie wird nicht
  aufgeführt, und der Index erscheint an seiner Tabelle.
- Die Spalten einer Tabelle sagen, welche zum Partitionsschlüssel gehören,
  welche Clustering-Spalten sind, in welcher Reihenfolge, und welche statisch.

## Zeilen

- Zeilen kommen in der Reihenfolge des Servers, seitenweise. Keine Spalte
  lässt sich sortieren: CQL ordnet Zeilen nur innerhalb einer ganz genannten
  Partition.
- Ein Filter auf jede Spalte funktioniert. Einer auf eine Spalte außerhalb des
  Schlüssels lässt den Server die ganze Tabelle lesen, was bei einer großen
  Tabelle die Zeit überschreiten kann.
- Filter vergleichen mit gleich, größer, kleiner, mindestens, höchstens und
  einem aus einer Liste. ScyllaDB ergänzt für Text „beginnt mit“ und
  „enthält“; `%` und `_` lassen sich nicht suchen, weil sein `LIKE` kein
  Escape kennt. Listen, Mengen, Zuordnungen, Tupel, benutzerdefinierte Typen,
  Blobs, Dauern und Zähler werden nicht gefiltert.
- Zahlen kommen genau wie gespeichert, bis zur letzten Ziffer eines `varint`
  oder `decimal`. Ein Zeitstempel erscheint in UTC. Listen, Mengen,
  Zuordnungen, Tupel und benutzerdefinierte Typen erscheinen als JSON; eine
  Zuordnung mit Schlüsseln, die kein Text sind, als Liste von Paaren. Ein Blob
  erscheint als `0x` und Hexadezimalziffern.
- Ein weiter Sprung nach vorn liest die Zeilen dazwischen, bis zu
  hunderttausend. Darüber hinaus blättern Sie von einer gelesenen Seite weiter.
- Die letzte Seite kann mehr versprechen und leer sein: Der Server sagt, ob
  mehr folgen könnte, bevor er nachgesehen hat.

## CQL-Konsole

**Neue Abfrage** unter **Abfragen** in der linken Leiste beginnt eine auf der
Verbindung, **Als Abfrage öffnen** über einer Tabelle eine auf dieser Tabelle.
Sie arbeitet wie die PostgreSQL-Konsole — Lesen, Ändern, Vervollständigung —
mit diesen Unterschieden:

- Die Sprache ist CQL. Der über dem Editor gewählte Keyspace ist der, in dem
  unqualifizierte Namen liegen; ein `USE` ändert ihn nur für den Rest dieses
  Laufs.
- Es gibt keine Transaktion. **Lesen** führt nur lesende Anweisungen aus:
  `SELECT`, `DESCRIBE` und `LIST`. **Auto-Commit** führt alles aus, aber eine
  Anweisung, die Zeilen oder Struktur ändert, läuft allein, weil Cassandra sie
  sofort behält und nicht zurücknehmen kann. Änderungen, die zusammen landen
  müssen, gehören in ein `BEGIN BATCH … APPLY BATCH`, das als eine Anweisung
  zählt.
- Parameter sind die von CQL, `:name`. Der Server sagt den Typ jedes einzelnen,
  und der Wert wird als dieser Typ gelesen; eine Liste, eine Menge, eine
  Zuordnung, ein Tupel oder ein benutzerdefinierter Typ wird als JSON
  geschrieben. **SQL null** sendet null.
- `CONSISTENCY`, `TRACING`, `COPY`, `SOURCE`, `PAGING` und die übrigen Befehle
  von cqlsh sind kein CQL und werden hier abgelehnt; führen Sie sie in cqlsh
  aus.
- **Stopp** hört auf, auf die Antwort zu warten. Dem Server lässt sich nicht
  sagen, eine Anweisung abzubrechen, also führt er sie trotzdem zu Ende.

## cqlsh

**Terminal** auf einer Verbindung öffnet cqlsh, angemeldet wie die Verbindung,
in dem Keyspace, den sie nennt. Auch für ScyllaDB ist es das cqlsh von
Cassandra; beide sprechen CQL. Es läuft in einem Container auf diesem Server,
also muss der Host von dort erreichbar sein, und eine Verbindung durch einen
SSH-Tunnel hat noch kein Terminal.

## Zeilen ändern

- In einer Tabelle werden Zellen bearbeitet, Blöcke eingefügt, Zeilen angelegt
  und gelöscht. Materialisierte Sichten, virtuelle Tabellen und die Keyspaces
  des Servers sind nur lesbar, ebenso eine Zählertabelle: Ein Zähler nimmt nur
  eine Addition an, die die Konsole schreiben kann.
- Eine Zeile wird über ihren Primärschlüssel gefunden. Die Spalten des
  Schlüssels werden nicht bearbeitet — sie entscheiden, wo die Zeile liegt —,
  und eine neue Zeile braucht für jede einen Wert.
- Eine Zeile, die jemand geändert hat, nachdem Sie die Seite gelesen haben,
  wird abgelehnt statt überschrieben. Lesen Sie die Seite erneut und
  wiederholen Sie die Änderung. Eine Änderung im selben Augenblick wie Ihre wird
  nicht erkannt: Cassandra hat keine Transaktion, die die Zeile hält.
- Listen, Mengen, Zuordnungen, Tupel und benutzerdefinierte Typen werden als
  das JSON geschrieben, als das sie erscheinen; eine Dauer in den Einheiten von
  CQL, etwa `1mo2d3h`.
- Eine statische Spalte hält einen Wert für die ganze Partition, also ändert
  ihre Bearbeitung auf einer Zeile sie auf allen Zeilen dieser Partition.
- Das Anlegen einer Zeile lehnt einen Schlüssel ab, den es schon gibt. Als
  Block eingefügte oder geladene Zeilen ersetzen eine Zeile mit demselben
  Schlüssel, so schreibt Cassandra.
- Ein Einfügen wird als Ganzes geprüft, bevor etwas geschrieben wird: ein
  Wert, den seine Spalte nicht aufnehmen kann, und nichts ändert sich.

## Die Struktur ändern

- Spalten einer Tabelle werden hinzugefügt und entfernt. Eine Spalte des
  Primärschlüssels wird nicht entfernt; eine, die ein Index oder eine
  materialisierte Sicht liest, lässt auch der Server nicht entfernen und sagt
  welche.
- Umbenennen lässt sich nur eine Spalte des Primärschlüssels: Etwas anderes
  benennt Cassandra nicht um. Standardwerte, Pflichtspalten außerhalb des
  Schlüssels und eine Typänderung gibt es in Cassandra nicht, also werden sie
  nicht angeboten.
- Ein Sekundärindex wird auf einer Spalte angelegt und entfernt. Cassandra 5
  bietet den speichergebundenen Index (SAI) und den klassischen, ScyllaDB
  seinen globalen. Keiner ist eindeutig.
- Materialisierte Sichten, virtuelle Tabellen und die Keyspaces des Servers
  werden nicht geändert.

## Eine Tabelle anlegen

- **Tabelle anlegen** auf einem Keyspace öffnet den Tabellen-Designer. Der Plan
  ist ein `CREATE TABLE` und ein `CREATE INDEX` je Index, gezeigt, bevor er
  läuft.
- Ein Primärschlüssel ist nötig. Auf der Optionsseite der Tabelle nennt
  **Partitionsschlüssel** die vorderen Spalten des Primärschlüssels, die
  entscheiden, auf welchem Knoten eine Zeile liegt; leer gelassen, ist es die
  erste Spalte. Der Rest des Primärschlüssels ordnet die Zeilen innerhalb einer
  Partition.
- Der Name einer Tabelle besteht aus Buchstaben, Ziffern und Unterstrichen;
  der einer Spalte darf alles sein. Eine Spalte darf eine Liste ihres Typs
  sein, aber eine Liste und eine Dauer gehören nicht in den Schlüssel.
- Eindeutige Schlüssel, Fremdschlüssel, Prüfungen, Standardwerte, berechnete
  Spalten, Sortierfolgen, Partitionierung nach Bereich, Liste oder Hash und
  Pflichtspalten außerhalb des Schlüssels gibt es in CQL nicht; der Designer
  sagt es an dem Objekt, das danach fragt.

## Der Bereich „Cluster“

- Nach den Keyspaces hält **Cluster**, was der Knoten über den Cluster sagt:
  **Knoten**, **Clients**, **Tabellengrößen**, **Einstellungen** und **Rollen**.
  Sie blättern wie eine Tabelle; Clients liest sich alle paar Sekunden neu.
  Tabellengrößen sind die eigene Schätzung des Knotens.
- Die `system`-Keyspaces stehen ebenfalls im Katalog, für alles, was diese
  Berichte auslassen.

## Suchen und herunterladen

- Das Suchfeld findet Keyspaces und Tabellen nach Namen und Tabellen nach dem
  Namen einer Spalte oder nach ihrem Kommentar.
- Herunterladen nimmt jede Zeile, die zu den Filtern einer Seite passt, nicht
  nur die Seite.

## Katalogaktionen

- **Neuer Keyspace** oben in der Verbindung, gehalten im Rechenzentrum des
  Knotens mit der gewählten Zahl von Replikaten.
- Auf einem Keyspace: **Tabelle anlegen** und **Keyspace entfernen**. Ein
  Keyspace wird erst entfernt, wenn Sie gesehen haben, was er enthält, und
  angekreuzt haben, alles darin zu entfernen.
- Auf einer Tabelle: **Leeren**, was jede Zeile löscht und die Tabelle
  behält, und **Entfernen**; auf einer materialisierten Sicht **Entfernen**.
  Eine Tabelle wird zusammen mit den materialisierten Sichten entfernt, die
  sie lesen, und die Vorschau nennt sie.
- Tabellen und Keyspaces lassen sich nicht umbenennen: CQL kennt keinen Weg
  dafür.

## Tabellen kopieren

**Kopieren** Sie Tabellen im Katalog und **fügen** Sie sie in einen Keyspace
einer anderen Cassandra- oder ScyllaDB-Verbindung oder derselben ein. Sie
kommen mit ihren Spalten, ihrem Partitions- und Clustering-Schlüssel und
dessen Reihenfolge, ihrem Kommentar, ihren Sekundärindizes und den
benutzerdefinierten Typen, die sie verwenden; das Fenster zeigt jede Anweisung
und führt vor **Kopieren** nichts aus.

- Die Typen, die dem Keyspace fehlen, werden zuerst angelegt, dann die
  Tabelle, dann ihre Zeilen und erst danach ihre Indizes.
- Eine Zählertabelle wird nicht kopiert: Ein Zähler lässt sich nicht per
  `INSERT` schreiben. Materialisierte Sichten werden nicht kopiert; eine, die
  eine kopierte Tabelle liest, wird im Fenster genannt.
- Scheitert die Kopie oder wird sie gestoppt, werden die angelegten Tabellen
  wieder entfernt.
- Nichts hält die Tabellen still, während sie gelesen werden: Zeilen, die
  inzwischen geschrieben werden, kommen an oder auch nicht.

In eine andere Art von Verbindung eingefügte Zeilen gehen den Weg der Zeilen
jeder Tabelle.

## Sicherungen

Für Cassandra und ScyllaDB noch nicht angeboten.

## Dashboards

Eine Cassandra-Verbindung kann an Dashboards berichten. Das Layout ist
**Cassandra-Knoten**: Clients, Größe und Partitionen des Keyspace der
Verbindung, wie der Knoten sie schätzt, und bei Cassandra Anfragen,
Lesevorgänge, Schreibvorgänge und Kompaktierungen pro Sekunde sowie die
wartende Arbeit. ScyllaDB hält diese Zähler in einem eigenen Monitoring-Endpunkt,
den diese Verbindung nicht liest.

## Ein eigener Server

**Neue Verbindung** bietet auf der Cassandra-Karte **Apache Cassandra hier
starten** und auf der ScyllaDB-Karte **ScyllaDB hier starten** an: einen auf
diesem Rechner gestarteten Knoten, gespeichert als Verbindung, angemeldet als
Superuser `cassandra` mit einem für ihn erfundenen Passwort. Ein
Cassandra-Knoten braucht ein bis zwei Minuten bis zur Antwort und setzt sein
Passwort selbst, sobald er antwortet. Mit Beispieldaten öffnet er sich auf
`demo_lab` — Organisationen und ihre Personen, Projekte und ihre Aufgaben,
zwanzigtausend Seitenaufrufe über dreißig Tage und eine Zählertabelle der
Aufrufe je Seite — mit etwas für jede Ansicht: eine statische Spalte, ein
benutzerdefinierter Typ, Sammlungen, eine Dauer, ein Sekundärindex, eine
materialisierte Sicht und eine Clustering-Reihenfolge, neueste zuerst.
