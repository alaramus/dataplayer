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
- Berichte: Größe der Datei, Sequenzen, Typen, Makros, DuckDBs Funktionen
- Alle Zeilen einer Tabelle, einer Sicht oder eines Berichts, heruntergeladen

## Was Sie ändern können

- Tabellendaten: Zellen, eingefügte Blöcke, neue und gelöschte Zeilen
- Spalten, Indizes und eindeutige Schlüssel
- Neue Tabellen, Objekt für Objekt entworfen oder aus Zeilen erstellt
- Schemas anlegen und löschen; Tabellen und Sichten umbenennen und löschen
- Tabellen mit ihrer Struktur kopiert, in eine andere DuckDB-Datei oder in
  diese
- Die ganze Datei, gesichert und wiederhergestellt
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

## Eine eigene Datenbank

**Neue Verbindung** bietet **DuckDB hier erstellen** an, auf die zwei Arten,
auf die ein Server gestartet wird. **Für mich einrichten** legt
`databases/dataplayer.duckdb` in Ihrem Speicher an, gefüllt mit einem Labor aus
Organisationen, Personen, Projekten und Aufgaben, und speichert die Verbindung
für Sie. **Selbst auswählen** fragt nach Name, Ordner und ob Beispieldaten
hinein sollen. Ein schon vergebener Name erhält eine Nummer, statt die Datei zu
ersetzen. Die Datei ist eine gewöhnliche: Umbenennen, Herunterladen oder
Löschen geht in **Dateien**.

Eine DuckDB-Datei, die Sie schon in einer **Dateien**-Verbindung sehen, lässt
sich von dort verbinden: **Als DuckDB verbinden** füllt dieses Fenster für Sie
aus.

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

## Zeilen bearbeiten

Mit dem Zugriff **Zeilen bearbeiten** wird eine Tabelle in ihrem Raster
bearbeitet wie eine PostgreSQL-Tabelle: Doppelklick auf eine Zelle, einen Block
einfügen, **Zeile einfügen**, Zeilen ankreuzen und **Ausgewählte Zeilen
löschen**.

- Eine Zeile wird über ihren Primärschlüssel wiedergefunden. Eine Tabelle ohne
  Schlüssel nimmt neue Zeilen an und ist sonst schreibgeschützt, da DuckDB eine
  Zeile beim Ändern verschiebt und zwei gleiche Zeilen halten kann. Eine Sicht
  ist schreibgeschützt.
- Hat jemand eine Zeile nach Ihrem Lesen geändert, wird Ihre Änderung
  abgelehnt, statt seine zu überschreiben. Neu laden und erneut versuchen.
- Schreiben Sie Werte so, wie das Raster sie zeigt: ein Datum als
  `2026-01-02`, einen Zeitpunkt mit seiner Zeitzone, Binärdaten als `0x…`.
  DuckDB liest sie nach dem Typ der Spalte, und ein Wert, den es nicht lesen
  kann, wird abgelehnt; in einem eingefügten Block werden die abgelehnten
  Zellen genannt, und nichts wird geschrieben.
- Listen, Structs, Maps und berechnete Spalten werden nicht im Raster
  bearbeitet; ändern Sie sie mit SQL in der Konsole.
- Eine Änderung, die Schlüssel, Prüfungen oder Pflichtspalten der Tabelle
  ablehnen, wird nicht ausgeführt, und die Regel wird genannt.
- DuckDB kann einen Schlüssel oder eine eindeutige Spalte einer Zeile, auf die
  andere Zeilen verweisen, nicht ändern, auch nicht auf einen freien Wert;
  andere Spalten dieser Zeile ändern sich.
- Eine Zelle eines Fremdschlüssels hat einen Pfeil, der die Zeile öffnet, auf
  die er zeigt, und **Was auf diese Zeile zeigt** öffnet die Zeilen, die hierher
  zeigen.

## Die Struktur ändern

**Struktur** einer Tabelle ändert sie wie eine PostgreSQL-Tabelle: eine Spalte
hinzufügen, umbenennen und löschen, ihren Standardwert setzen oder entfernen,
einen Wert verlangen oder nicht mehr verlangen, ihren Typ ändern, Indizes
hinzufügen und löschen, einen eindeutigen Schlüssel hinzufügen.

- DuckDB nimmt jede Änderung an Ort und Stelle vor, in einer Transaktion;
  nichts wird neu aufgebaut.
- Eine Änderung, der die Zeilen schon widersprechen, wird nicht vorgenommen,
  und die Anzahl wird gezeigt: Zeilen ohne Wert, Werte, die sich nicht in den
  neuen Typ umwandeln lassen, Werte, die sich wiederholen.
- Ein Standardwert wird vor dem Setzen gegen den Typ der Spalte geprüft.
- DuckDB kann einer bestehenden Tabelle keinen Fremdschlüssel und keine Prüfung
  hinzufügen und keine ihrer Einschränkungen entfernen, auch den
  Primärschlüssel nicht. Kopieren Sie die Tabelle stattdessen in eine, die so
  entworfen ist, wie Sie sie wollen.
- Eine Tabelle mit eigenem Index oder eine, auf die der Fremdschlüssel einer
  anderen Tabelle zeigt, nimmt nur eine neue Spalte, einen Standardwert und
  einen neuen Index an. Eine Spalte umbenennen, löschen oder ihren Typ ändern,
  einen Wert verlangen und einen eindeutigen Schlüssel hinzufügen wird
  abgelehnt.
- DuckDB benennt und löscht eine Spalte, ohne auf die Sichten zu achten, die
  sie lesen. Deshalb wird nach der Änderung jede Sicht neu gelesen, und eine,
  die die Änderung zerbrechen würde, lehnt sie mit ihrem Namen ab.
- Was DuckDB selbst ablehnt, etwa eine Spalte zu löschen, die ein Index
  abdeckt, wird mit DuckDBs eigenen Worten gesagt.
- Angeboten werden DuckDBs Typen: Text, Ganzzahlen in vier Breiten,
  Gleitkommazahl, Dezimalzahl, Wahrheitswert, Datum, Uhrzeit, Datum und Uhrzeit
  mit oder ohne Zeitzone, Intervall, UUID, JSON und Binärdaten.
- DuckDB baut eine Art Index, einen adaptiven Radix-Baum, benannt nach der
  Tabelle und ihren Spalten. Einschränkungen benennt DuckDB selbst.

## Eine Tabelle erstellen

**Tabelle erstellen** im Aktionsmenü eines Schemas öffnet den Tabellen-Designer
wie bei PostgreSQL. Der Plan ist ein `CREATE TABLE`, ein `CREATE INDEX` je
Index und die Kommentare, zusammen ausgeführt: Die Tabelle entsteht ganz oder
gar nicht.

- Eine Identitätsspalte ist eine eigene Sequenz, `<Tabelle>_<Spalte>_seq`, die
  vor der Tabelle angelegt wird; der Standardwert der Spalte nimmt ihren
  nächsten Wert. Sie kann bei jedem Wert beginnen und um jeden Betrag
  weiterzählen. Sie übernimmt einen Wert, den Sie hineinschreiben, und kann
  deshalb nicht ALWAYS sein.
- Eine generierte Spalte wird bei jedem Lesen berechnet; eine, die gespeichert
  werden soll, wird so angelegt, mit einer Warnung.
- Was DuckDB nicht hat, wird an dem Objekt markiert, das danach fragt, bevor
  Sie den Plan prüfen können: eine nicht protokollierte oder partitionierte
  Tabelle, ein Fremdschlüssel, der kaskadiert, auf null oder auf einen
  Standardwert setzt oder in ein anderes Schema zeigt, ein beim Commit
  geprüfter Schlüssel, ein Index über einen Teil der Zeilen oder mit
  zusätzlichen Spalten.
- Ein Standardwert wird beim Erstellen des Plans gegen den Typ seiner Spalte
  geprüft.
- Angegebene Namen von Einschränkungen werden nicht übernommen; DuckDB benennt
  Einschränkungen selbst.
- Kommentare zur Tabelle und zu ihren Spalten bleiben erhalten.
- Sortierungen sind DuckDBs eigene: `NOCASE`, `NOACCENT` und `NFC`.
- Als Tabelle behaltene Zeilen oder eine in eine Tabelle geladene Datei kommen
  in einem Zug mit der Tabelle. Ein Wert, den DuckDB nicht als Typ seiner
  Spalte lesen kann, lässt die Tabelle unerstellt.

## Berichte

**System** im Katalog enthält fünf Berichte. Sie werden wie Tabellen gelesen
und lassen sich sortieren, filtern, herunterladen und als Diagramm zeigen.
**Anweisung anzeigen** zeigt das SQL, das ein Bericht ausführt.

- **Datenbank**: DuckDBs Version, die Größe der Datei, ihre belegten und freien
  Blöcke und das Write-Ahead-Log.
- **Sequenzen**, mit Start, Schritt und Grenzen. Eine Identität aus dem
  Tabellen-Designer ist eine davon.
- **Typen** der Datei selbst: Enums, Structs und andere Namen für einen Typ.
- **Makros**: in SQL geschriebene Funktionen, die in der Datei gespeichert
  sind, mit Parametern und Rumpf.
- **Funktionen**, die in DuckDB eingebaut sind, und wie viele Signaturen jede
  hat.
- Die Einstellungen der Engine werden nicht gezeigt: Sie nennen Ordner des
  Servers und sind hier fest.

## Aktionen im Katalog

- **Neues Schema** oben in der Verbindung. **Schema löschen** löscht jedes
  Schema außer `main`; eines, das etwas enthält, braucht **Auch alles darin
  löschen**, und die Frage zählt auf, was verschwindet. Ein Schema lässt sich
  in DuckDB nicht umbenennen.
- **Umbenennen** einer Tabelle oder Sicht. Danach wird jede Sicht neu gelesen,
  und eine, die den alten Namen las, lehnt die Umbenennung ab und wird genannt.
  DuckDB benennt keine Tabelle um, die einen eigenen Index hat oder auf die der
  Schlüssel einer anderen Tabelle zeigt.
- Eine Tabelle mit eigenem Fremdschlüssel wird nicht umbenannt: DuckDB behielte
  den alten Namen in der Tabelle, auf die sie zeigt, und diese könnte dann
  weder Zeilen löschen noch gelöscht werden.
- **Löschen** einer Relation oder mehrerer zusammen. Das Löschen wird zuerst
  probiert und rückgängig gemacht, sodass die Frage die Sichten nennt, die
  nicht mehr funktionieren würden. Eine Tabelle, auf die der Schlüssel einer
  anderen zeigt, wird abgelehnt, wenn jene nicht mitgelöscht wird. Eine
  Sequenz, aus der nur die gelöschten Tabellen Werte nehmen, wie die einer
  Identität, wird mitgelöscht.
- **Aus CSV laden** macht aus einer Datei eine Tabelle im Schema, jede Spalte
  als `VARCHAR`.
- **Modell als Code** schreibt ein Schema oder eine Auswahl für ein ORM oder
  ein Diagramm aus.
- Zwischen Schemas wird nichts verschoben: DuckDB kann das nicht.

## Tabellen kopieren

**Kopieren** Sie Tabellen im Katalog und **Fügen** Sie sie in ein Schema einer
anderen DuckDB-Verbindung **ein** oder dieser. Sie kommen mit ihren Spalten,
Standardwerten, Schlüsseln, Prüfungen, Indizes und Kommentaren an; das Fenster
fragt dasselbe wie bei PostgreSQL, zeigt jede Anweisung und führt nichts vor
**Kopieren** aus.

- Jeder Wert kommt genau so an, wie er war, Listen, Structs und Maps
  eingeschlossen. Eine Tabelle mit einer `UNION`-Spalte wird nicht kopiert: Ihr
  Text sagt nicht, welches Element ein Wert ist.
- Eine Spalte, deren Standardwert den nächsten Wert einer Sequenz nimmt, wie
  bei einer Identität, erhält in der Kopie eine eigene Sequenz, die dort
  weiterzählt, wo die des Originals es täte.
- DuckDB prüft einen Fremdschlüssel sofort, also wird eine Tabelle nach den
  Tabellen der Kopie angelegt und gefüllt, auf die sie zeigt. Ein Schlüssel
  kann nur in sein eigenes Schema zeigen.
- Die Kopie ist eine Transaktion: Tabellen, Zeilen und Indizes kommen zusammen
  an oder gar nicht.

## Sicherungen

**Sicherungen** im Aktionsmenü des Katalogs funktionieren wie bei PostgreSQL,
für die Datei, die die Verbindung öffnet.

- Die Sicherung ist eine Kopie der Datei, gezogen, nachdem DuckDB sein Log in
  sie geschrieben hat. Solange ein anderes Programm in die Datei schreibt, wird
  sie abgelehnt.
- **Wiederherstellen** ersetzt alles in der Datei durch die Sicherung. Eine
  Datei, die keine DuckDB-Datenbank ist, wird abgelehnt, bevor etwas
  geschrieben wird.

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

- Eine Datei auf einem SSH-Server oder in einer anderen Verbindung lässt sich
  nicht als Datenbank öffnen.
