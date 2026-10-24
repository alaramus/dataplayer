# SQLite

Eine SQLite-Datenbankdatei in Ihrem persönlichen Speicher. Sie durchsuchen
ihre Tabellen und Ansichten, lesen und bearbeiten ihre Zeilen Seite für Seite,
sehen, wie eine Tabelle aufgebaut ist, lesen die DDL, die die Datei für sie
aufbewahrt, und führen SQL in einer Konsole aus.
Wie Verbindungen im Allgemeinen funktionieren, steht auf der Seite
[Verbindungen](connections.md).

## Was Sie sehen können

- Tabellen, Ansichten und virtuelle Tabellen und ihre Zeilen, sortiert und
  gefiltert
- Die Spalten, Schlüssel, Prüfungen und Indizes einer Tabelle und die Tabellen,
  auf die sie verweist
- Die DDL einer Relation, wie die Datei sie aufbewahrt, mit ihren Indizes und
  Triggern
- Die Ergebnisse des SQL, das Sie schreiben, und den Plan von SQLite für eine
  Abfrage
- Alle passenden Zeilen, als Datei heruntergeladen
- Was die Datei über sich selbst sagt: ihren Aufbau, ihre Integrität,
  verletzte Schlüssel, Trigger und was das SQLite dieses Servers bietet
- Wohin der Fremdschlüssel einer Zeile führt und was auf sie verweist

## Was Sie ändern können

- Tabellendaten: Zellen bearbeiten, Blöcke einfügen, Zeilen hinzufügen und
  löschen
- Spalten, Indizes, eindeutige Schlüssel und Fremdschlüssel
- Neue Tabellen, Objekt für Objekt entworfen oder aus Zeilen erstellt
- Tabellen und Ansichten: umbenennen, löschen
- Tabellen mit ihrer Struktur kopiert, in eine andere SQLite-Datei oder in
  diese
- Die ganze Datei, gesichert und wiederhergestellt
- Daten und Struktur, per SQL in der Konsole

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach:

- **Datenbankdatei**: dem Pfad der Datei in Ihrem persönlichen Speicher, etwa
  `data/shop.db`. Legen Sie die Datei zuerst dort ab, über eine Verbindung vom
  Typ **Dateien**. Ein Pfad außerhalb Ihres Speichers wird abgelehnt.
- **Datei anlegen, wenn sie fehlt**: Setzen Sie das Häkchen, um mit einer
  leeren Datenbank zu beginnen. Ohne es scheitert die Prüfung an einer Datei,
  die nicht da ist, sodass ein vertippter Pfad keine leere Datei hinterlässt.
  Der Ordner muss bereits existieren.

Eine Datenbankdatei, die Sie schon in einer Verbindung vom Typ **Dateien**
sehen, lässt sich von dort verbinden: **Als SQLite verbinden** füllt dieses
Fenster für Sie aus.

Die Datei wird für jede Anfrage neu geöffnet, sodass eine über **Dateien**
ersetzte Datei so gelesen wird, wie sie jetzt ist.

Was eine Verbindung zu der Datei nicht kann, was auch immer die Datei enthält:
eine zweite Datei öffnen (`ATTACH`, `VACUUM INTO`), eine Erweiterung laden oder
irgendetwas anderes auf dem Server erreichen. Eine Datei kann jeder hochladen,
deshalb kann eine Ansicht oder ein Trigger darin auch keine Funktion mit
Nebenwirkungen aufrufen.

## Der Katalog

- Die erste Ebene ist `main`, das einzige Schema der Datei.
- Darin liegen ihre Tabellen, Ansichten und virtuellen Tabellen. Ein Klick
  öffnet die Zeilen in einem Tab.
- Die eigenen Tabellen von SQLite (`sqlite_schema`, `sqlite_sequence`,
  `sqlite_stat1`) und die Tabellen, die eine virtuelle Tabelle für sich selbst
  führt, etwa die eines Volltextindex, sind als Systemtabellen markiert.
- Wie viele Zeilen eine Tabelle ungefähr hat, sagt sie erst, nachdem `ANALYZE`
  auf der Datei gelaufen ist. Nichts zählt die Zeilen.
- **Details** zeigt, wie viele Spalten, Indizes und Einschränkungen eine
  Relation hat.
- **DDL anzeigen** zeigt die Anweisung `CREATE TABLE` oder `CREATE VIEW`, die
  die Datei aufbewahrt, gefolgt von den Indizes und Triggern der Tabelle.
- Eine virtuelle Tabelle mit einem Modul, das dieser Server nicht hat, wird
  aufgeführt und sagt das, wenn sie geöffnet wird.
- **System** nach `main` ist ein Abschnitt mit Berichten (siehe **Berichte**
  unten).
- Die Suche in der Kopfzeile findet Tabellen und Ansichten nach Namen und nach
  ihren Spalten.

## Zeilen lesen

Eine Tabelle öffnet sich als Raster, Seite für Seite, sortiert und gefiltert
wie eine PostgreSQL-Tabelle. Jede Spalte lässt sich sortieren. Was eine Spalte
anbietet, hängt vom Typ ab, mit dem sie deklariert wurde: Vergleiche für
Zahlen, Daten und Text; enthält und beginnt mit für Text; leer oder nicht leer
für jede Spalte.

- Die Seiten folgen dem Primärschlüssel oder sonst der Reihenfolge, in der die
  Zeilen geschrieben wurden (der `rowid`). Eine Ansicht kommt in der
  Reihenfolge, in der SQLite sie liefert.
- Ein `%` oder `_` in einem Textfilter wird als es selbst gesucht.
  Textfilter beachten bei lateinischen Buchstaben keine Groß- und
  Kleinschreibung.
- Eine Spalte ohne Typ wird als Text gefiltert.

Wie Werte gezeigt werden:

- ein Wert als das, was er ist, was auch immer seine Spalte sagt: SQLite lässt
  eine `INTEGER`-Spalte Text enthalten, und Text wird als Text gezeigt;
- Binärwerte hexadezimal, etwa `0x00FF`, in jeder Spalte;
- eine `BOOLEAN`-Spalte als `true` oder `false`, wo sie 0 oder 1 enthält;
- Text, der kein gültiges UTF-8 ist, hexadezimal statt mit Zeichen, die nicht
  da sind;
- große Ganzzahlen genau.

## Zeilen bearbeiten

Mit Zugriff **Zeilen bearbeiten** wird eine Tabelle in ihrem Raster bearbeitet
wie eine PostgreSQL-Tabelle: Doppelklick auf eine Zelle, einen Block einfügen,
**Zeile einfügen**, Zeilen markieren und **Ausgewählte Zeilen löschen**.
Ansichten, virtuelle Tabellen und die eigenen Tabellen von SQLite sind nur
lesbar, und eine generierte Spalte wird berechnet statt geschrieben.

- Eine Zeile wird über ihren Primärschlüssel wiedergefunden oder über ihre
  `rowid`, wenn die Tabelle keinen hat.
- Hat jemand eine Zeile geändert, nachdem Sie sie gelesen haben, in welcher
  Spalte auch immer, wird Ihre Änderung abgelehnt, statt seine zu
  überschreiben. Laden Sie neu und versuchen Sie es noch einmal.
- Schreiben Sie Werte so, wie das Raster sie zeigt: binär als `0x…` in einer
  `BLOB`-Spalte, `true` oder `false` in einer `BOOLEAN`-Spalte. Eine Spalte
  ohne Typ lässt eine Zahl eine Zahl sein. Was jede andere Spalte bekommt,
  speichert SQLite so umgewandelt, wie ihr Typ es sagt.
- Eine `STRICT`-Tabelle lehnt einen Wert des falschen Typs ab, bevor etwas
  geschrieben wird, und die Zellen mit solchen Werten werden genannt. Von einem
  eingefügten Block landet nichts, bevor nicht alles landen kann.
- Eine Änderung, die die Schlüssel, Prüfungen oder Pflichtspalten der Tabelle
  ablehnen, wird nicht vorgenommen und sagt, welche Regel sie abgelehnt hat.
  Die Fremdschlüssel der Datei werden durchgesetzt.
- Eine Zelle in einem Fremdschlüssel hat einen Pfeil, der die Zeile öffnet,
  auf die sie verweist, und **Was auf diese Zeile verweist** öffnet die
  Zeilen, die hierher verweisen.

## Die Struktur ändern

**Struktur** einer Tabelle ändert sie wie eine PostgreSQL-Tabelle: eine Spalte
hinzufügen, umbenennen und löschen, ihren Standardwert setzen oder entfernen,
einen Wert verlangen oder nicht mehr verlangen, ihren Typ ändern, Indizes,
eindeutige Schlüssel und Fremdschlüssel hinzufügen und löschen.

- SQLite selbst kann nur eine Spalte hinzufügen, die leer sein darf, und eine
  umbenennen. Für alles andere wird die Tabelle neu aufgebaut, so wie die
  Dokumentation von SQLite es beschreibt: eine neue Tabelle, die Zeilen mit
  ihrer `rowid` kopiert, die alte ersetzt, ihre Indizes und Trigger neu
  angelegt. Was die Änderung nicht berührt — `AUTOINCREMENT`, `DEFERRABLE`,
  Kommentare —, bleibt, wie es geschrieben ist.
- Eine Änderung, der die Zeilen schon widersprechen, wird nicht vorgenommen,
  und die Anzahl wird gezeigt: Zeilen ohne Wert, Werte, die sich wiederholen,
  Zeilen, die auf nichts verweisen.
- Eine Spalte mit einem Typ nimmt in SQLite jeden Wert, deshalb wird eine
  Typänderung nur in einer `STRICT`-Tabelle abgelehnt, mit der Anzahl der
  Werte, die sie nicht aufnehmen kann.
- Das Löschen einer Spalte löscht die Schlüssel und Indizes über ihr. Eine
  Prüfung oder Ansicht, die die Spalte liest, lehnt das Löschen ab und sagt,
  welche.
- Die angebotenen Typen sind die von SQLite: Text, Ganzzahl, Gleitkommazahl,
  Zahl, Wahrheitswert, Datum, Datum und Uhrzeit, JSON, UUID und binär. Einer
  `STRICT`-Tabelle werden ihre eigenen angeboten: Text, Ganzzahl,
  Gleitkommazahl, binär und beliebiger Wert.
- SQLite baut eine Art von Index, einen B-Baum, und benennt, was es anlegt,
  nach der Tabelle und ihren Spalten.

## Eine Tabelle erstellen

**Tabelle erstellen** im Aktionsmenü von `main` öffnet den Tabellen-Designer
wie bei PostgreSQL. Der Plan ist ein `CREATE TABLE` und ein `CREATE INDEX` je
Index, zusammen ausgeführt: Die Tabelle entsteht ganz oder gar nicht.

- Eine Identitätsspalte ist die eigene Zeilennummer von SQLite: eine Ganzzahl,
  die der ganze Primärschlüssel ist, geschrieben
  `INTEGER PRIMARY KEY AUTOINCREMENT`. Sie kann überall beginnen, zählt in
  Einerschritten und nimmt einen Wert an, den Sie hineinschreiben.
- Was SQLite nicht hat, wird am Objekt markiert, das danach fragt, bevor Sie
  den Plan prüfen können: eine nicht protokollierte oder partitionierte
  Tabelle, ein beim Festschreiben geprüfter eindeutiger Schlüssel, Nullwerte
  zuerst oder zuletzt sortiert, zusätzliche Spalten in einem Index.
- SQLite hat, was MySQL fehlt: einen Index über einen Teil der Zeilen, einen
  beim Festschreiben geprüften Fremdschlüssel, `SET DEFAULT` und einen Index
  über einen Ausdruck.
- Kommentare werden nicht aufbewahrt; der Plan sagt das.
- Sortierungen sind die von SQLite: `BINARY`, `NOCASE` und `RTRIM`.
- Als Tabelle behaltene Zeilen oder eine hineingeladene Datei kommen in einem
  Zug mit der Tabelle an.

## Berichte

**System** im Katalog enthält acht Berichte. Sie werden wie Tabellen gelesen
und lassen sich sortieren, filtern, herunterladen und als Diagramm zeigen.
**Anweisung anzeigen** zeigt das SQL, das ein Bericht ausführt.

- **Datei**: Seitengröße und -anzahl, die Größe der Datei, freie Seiten,
  Kodierung, Journalmodus, Auto-Vacuum und die Versionsnummern, die die Datei
  führt.
- **Integrität**: die schnelle Prüfung jeder Seite durch SQLite: `ok` oder was
  beschädigt ist. Sie liest die ganze Datei und wird deshalb erst beim Öffnen
  gelesen.
- **Verletzte Fremdschlüssel**: Zeilen, deren Schlüssel auf nichts verweist,
  geschrieben von einem Programm, das sie nicht durchgesetzt hat.
- **Trigger** mit ihren Definitionen.
- **Funktionen**, **Module** und **Sortierungen**, die das SQLite dieses
  Servers bietet, und die **Kompilieroptionen**, mit denen es gebaut wurde.

## Aktionen im Katalog

- **Umbenennen** einer Tabelle oder Ansicht. Was auf eine Tabelle verweist,
  folgt ihr. Eine Ansicht wird unter dem neuen Namen neu angelegt; eine
  Ansicht, die sie unter ihrem alten Namen liest, lehnt die Umbenennung ab und
  wird genannt.
- **Löschen** einer Relation oder mehrerer zusammen. Das Löschen wird zuerst
  ausprobiert und rückgängig gemacht, sodass die Rückfrage zeigt, was es tun
  würde: die Trigger, die mitgehen, die Tabellen, die auf sie verweisen, die
  Ansichten, die sie lesen. Hat eine Tabelle, die auf sie verweist, noch Zeilen
  und kaskadiert nicht, wird das Löschen mit diesem Grund abgelehnt. Tabellen,
  die aufeinander verweisen, lassen sich zusammen löschen.
- **Aus CSV laden** erstellt aus einer Datei eine Tabelle in `main`, jede
  Spalte als `TEXT`.
- **Modell als Code** schreibt `main` oder eine Auswahl für ein ORM oder ein
  Diagramm aus.

## Tabellen kopieren

**Kopieren** Sie Tabellen im Katalog und **Fügen** Sie sie in `main` einer
anderen SQLite-Verbindung **ein** oder dieser. Sie kommen mit ihren Spalten an,
wie die Datei sie schreibt, mit ihren Schlüsseln, Prüfungen, Indizes und
Optionen wie `STRICT`; das Fenster fragt dasselbe wie bei PostgreSQL, zeigt
jede Anweisung und führt nichts vor **Kopieren** aus.

- Trigger bleiben zurück und werden im Fenster genannt. Ansichten und
  virtuelle Tabellen werden so nicht kopiert.
- Ein Index wird nach der neuen Tabelle benannt, da zwei Indizes einer Datei
  keinen Namen teilen können.
- Das Kopieren ist eine Transaktion: Die Tabellen, ihre Zeilen und ihre
  Indizes kommen zusammen an oder gar nicht. Eine Zeile, deren Fremdschlüssel
  in der Kopie auf nichts verweist, lässt es am Ende scheitern, und nichts
  bleibt zurück.

In eine Verbindung einer anderen Art eingefügte Zeilen gehen den Weg, den die
Zeilen jeder Tabelle gehen.

## Sicherungen

**Sicherungen** im Aktionsmenü des Katalogs funktionieren wie bei PostgreSQL,
für die Datei, die die Verbindung öffnet.

- Die Sicherung ist eine Kopie der Datei, die SQLite selbst anfertigt; sie ist
  deshalb vollständig, auch wenn gerade jemand in die Datei schreibt.
- **Wiederherstellen** ersetzt alles in der Datei durch die Sicherung. Eine
  Datei, die keine SQLite-Datenbank ist oder die SQLite für beschädigt hält,
  wird abgelehnt, bevor etwas geschrieben wird.

## SQL-Konsole

**Neue Abfrage** unter **Abfragen** in der linken Leiste startet eine auf der
Verbindung, und **Als Abfrage öffnen** über einer Tabelle startet eine auf
dieser Tabelle. Sie funktioniert wie die PostgreSQL-Konsole — Lesen,
Änderungen sofort festgeschrieben oder in einer Transaktion **Manuell**
gehalten, **Erklären**, Vervollständigung und Formatierung. SQLite ändert die
Struktur innerhalb einer Transaktion, deshalb ist ein `CREATE`, `ALTER` oder
`DROP` Teil der Transaktion um ihn herum, kann in einer manuellen gehalten
werden und wird zuerst ausprobiert und rückgängig gemacht, bevor die Konsole
Sie danach fragt.

- Das Schema ist immer `main`.
- Parameter werden `:name` geschrieben.
- `ANALYZE`, `VACUUM` und `REINDEX` laufen für sich, außerhalb einer
  Transaktion.
- Ein `PRAGMA`, das etwas berichtet, etwa `PRAGMA table_info(items)` oder
  `PRAGMA integrity_check`, ist ein Lesen. Ein `PRAGMA`, das einen Wert setzt,
  wird nicht ausgeführt.
- Die Fremdschlüssel, die die Datei deklariert, werden durchgesetzt, was
  SQLite von sich aus nur tut, wenn ein Programm darum bittet.
- Trigger werden nicht aus der Konsole geändert, und keine andere Datei kann
  aus ihr geöffnet werden (`ATTACH`).
- **Erklären** zeigt den Plan von SQLite: eine Zeile je Schritt, ohne Kosten,
  da SQLite keine angibt.
- **Stoppen** und das Zeitlimit beenden eine Anweisung, wo sie gerade ist.
- Eine fehlgeschlagene Anweisung in einer Transaktion, die Sie halten, lässt
  die Transaktion offen.

## Was SQLite hier noch nicht hat

- Eine Datei auf einem SSH-Server oder in einer anderen Verbindung lässt sich
  nicht als Datenbank öffnen.
