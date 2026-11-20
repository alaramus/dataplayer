# DuckDB

Eine DuckDB-Datenbankdatei in Ihrem persönlichen Speicher. Sie durchsuchen ihre
Schemas, Tabellen und Sichten, lesen ihre Zeilen seitenweise, sehen, wie eine
Tabelle aufgebaut ist, und lesen die DDL, die die Datei für sie aufbewahrt.
Wie Verbindungen allgemein funktionieren, steht auf der Seite
[Verbindungen](connections.md).

## Was Sie sehen können

- Schemas, Tabellen und Sichten und ihre Zeilen, sortiert und gefiltert
- Spalten, Schlüssel, Prüfungen, Indizes und verwiesene Tabellen einer Tabelle
- Die DDL einer Relation, wie die Datei sie aufbewahrt, mit ihren Indizes
- Listen, Structs und Maps, als JSON gezeigt
- Die Ergebnisse Ihres SQL und DuckDBs Plan für eine Abfrage

## Was Sie ändern können

- Daten und Struktur, über SQL in der Konsole

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach:

- **Datenbankdatei**: dem Pfad der Datei in Ihrem persönlichen Speicher, etwa
  `data/shop.duckdb`. Legen Sie die Datei zuerst über eine Verbindung
  **Dateien** dort ab. Ein Pfad außerhalb Ihres Speichers wird abgelehnt.
- **Datei anlegen, wenn sie fehlt**: ankreuzen, um mit einer leeren Datenbank
  zu beginnen. Ohne das scheitert eine fehlende Datei an der Prüfung, sodass
  ein vertippter Pfad keine leere Datei hinterlässt. Der Ordner muss schon
  existieren.

Die Datei wird für jede Anfrage neu geöffnet und danach geschlossen, sodass
zwischen zwei Anfragen auch Ihr eigenes DuckDB, ein Notebook oder ein Skript
sie öffnen kann. Solange ein anderes Programm sie offen hält, meldet diese
Verbindung, dass die Datei verwendet wird.

Eine Datei, die ein neueres DuckDB als das dieses Servers geschrieben hat, lässt
sich womöglich nicht öffnen, und eine von diesem Server, einem DuckDB 2,
geschriebene Datei womöglich nicht in DuckDB 1.

Was eine Verbindung zur Datei nicht kann, was immer die Datei enthält: eine
Datei außerhalb Ihres persönlichen Speichers lesen, das Netz erreichen, eine
Erweiterung installieren oder laden oder eine große Sortierung auf die Platte
auslagern. Eine Sicht in der Datei, die eine Datei anderswo liest, wird beim
Öffnen abgelehnt. Dateien Ihres Speichers werden von seiner Wurzel aus mit `~/`
benannt, etwa `~/data/sales.parquet`.

## Der Katalog

- Die erste Ebene sind die Schemas der Datei, darunter `main`.
- In jedem liegen seine Tabellen und Sichten. Ein Klick öffnet ihre Zeilen in
  einem Tab.
- Eine Tabelle nennt ungefähr, wie viele Zeilen sie hat, wie DuckDB es ohne
  Zählen schätzt.
- **Details** nennt, wie viele Spalten, Indizes und Einschränkungen eine
  Relation hat.
- **DDL anzeigen** zeigt die Anweisung `CREATE TABLE` oder `CREATE VIEW`, die
  die Datei aufbewahrt, gefolgt von den Indizes der Tabelle.
- DuckDB benennt Einschränkungen selbst, etwa `items_id_pkey`, auch wenn die
  Anweisung ihnen einen Namen gab.

## Zeilen lesen

Eine Tabelle öffnet sich als Raster, seitenweise, sortiert und gefiltert wie
eine PostgreSQL-Tabelle. Was eine Spalte anbietet, hängt von ihrem Typ ab:
Vergleiche für Zahlen, Daten und Text; gleich oder ungleich für UUIDs, Enums und
Intervalle; enthält und beginnt mit für Text, JSON, Listen und Structs; leer
oder nicht leer für jede Spalte.

- Seiten folgen dem Primärschlüssel, sonst der Reihenfolge, in der DuckDB die
  Zeilen hält. Eine Sicht steht in der Reihenfolge, die DuckDB liefert.
- Eine Liste, ein Struct oder eine Map lässt sich nicht sortieren.
- Einen Filterwert liest DuckDB als Typ der Spalte: ein Datum als
  `2026-01-02`, einen Zeitpunkt mit seiner Zeitzone, eine Dezimalzahl bis zur
  letzten Stelle. Ein Wert, den DuckDB so nicht lesen kann, wird abgelehnt.
- Ein `%` oder `_` in einem Textfilter wird als es selbst gesucht.
  Textfilter ignorieren Groß- und Kleinschreibung.

Wie Werte gezeigt werden, so wie DuckDB sie schreibt:

- große Ganzzahlen und Dezimalzahlen exakt;
- ein Zeitpunkt mit Zeitzone in UTC;
- Binärwerte hexadezimal, etwa `0xAA00`;
- ein Intervall als `1 year 2 days 03:00:00`;
- eine Liste, ein Struct, eine Map oder eine Union als JSON.

## SQL-Konsole

**Neue Abfrage** unter **Abfragen** in der linken Leiste startet eine auf der
Verbindung, und **Als Abfrage öffnen** über einer Tabelle startet eine auf
dieser Tabelle. Sie funktioniert wie die PostgreSQL-Konsole — Lesen,
Änderungen sofort festgeschrieben oder in einer Transaktion **Manuell**
gehalten, **Erklären**, Vervollständigung und Formatierung. DuckDB ändert die
Struktur innerhalb einer Transaktion, deshalb ist ein `CREATE`, `ALTER` oder
`DROP` Teil der Transaktion um ihn herum, und ein Löschen wird zuerst
ausprobiert und rückgängig gemacht, bevor die Konsole Sie danach fragt.

- Dateien Ihres Speichers werden als `~/…` gelesen, etwa
  `SELECT * FROM '~/data/sales.parquet'`. Laden Sie eine in eine Tabelle mit
  `INSERT INTO t SELECT * FROM '~/data/sales.csv'`.
- Parameter werden `$name` geschrieben.
- Das Schema wird über dem Editor gewählt; `USE` und `SET` werden nicht
  ausgeführt.
- Nicht ausgeführt, jeweils mit Grund: `ATTACH`, `COPY`, `EXPORT` und
  `IMPORT DATABASE`, `INSTALL` und `LOAD`, `PREPARE` und Geheimnisse.
- Eine fehlgeschlagene Anweisung in einer gehaltenen Transaktion beendet sie:
  Es bleibt nur **Zurückrollen**.
- Solange Sie eine Transaktion halten, bleibt die Datei offen, und kein anderes
  Programm kann sie öffnen.
- In einer gehaltenen Transaktion lässt sich ein Löschen nicht zuerst
  ausprobieren, da DuckDB keine Sicherungspunkte hat; führen Sie es im
  Auto-Commit aus.
- **Erklären** zeigt DuckDBs Plan: seine Operatoren und die erwarteten Zeilen.
- **Stoppen** und das Zeitlimit beenden eine Anweisung dort, wo sie ist.

## Was DuckDB hier noch nicht hat

- Zeilen bearbeiten, die Struktur ändern, Katalogaktionen, alle Zeilen
  herunterladen, Sicherungen und Tabellen kopieren. Sie kommen später.
- Eine Tabelle ohne Primärschlüssel bleibt auch dann schreibgeschützt: DuckDB
  verschiebt eine Zeile beim Ändern, und nichts anderes benennt sie.
- Eine Datei auf einem SSH-Server oder in einer anderen Verbindung lässt sich
  nicht als Datenbank öffnen.
