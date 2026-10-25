# ClickHouse

Ein ClickHouse-Server, erreichbar über seine HTTP-Schnittstelle. Sie
durchsuchen seine Datenbanken, lesen Tabellen und Ansichten seitenweise, sehen,
wie eine Tabelle aufgebaut ist, lesen ihre DDL, wie der Server sie ausgibt,
und führen SQL in einer Konsole aus.
Wie Verbindungen allgemein funktionieren, erfahren Sie auf der Seite
[Verbindungen](connections.md).

## Was Sie sehen können

- Datenbanken, Tabellen, Ansichten und materialisierte Ansichten
- Serverseitig sortierte und gefilterte Zeilen, Werte wie gespeichert
- Spalten, Primär- und Sortierschlüssel, Überspringindizes und Prüfungen
- DDL einer Relation, wie der Server sie ausgibt
- Größe, Partitionen und letzten Schreibzeitpunkt einer Tabelle
- Ergebnisse Ihres SQL und den Abfrageplan des Servers
- Jede passende Zeile, als Datei heruntergeladen
- Abfragen, Mutationen, Merges, Tabellengrößen, Datenträger und Einstellungen
- Serverzähler in einem Dashboard

## Was Sie ändern können

- Tabellendaten: Zellen bearbeiten, Blöcke einfügen, Zeilen einfügen und löschen
- Spalten und Überspringindizes von MergeTree-Tabellen
- Neue Tabellen, im Entwurf oder aus Zeilen erstellt
- Datenbanken erstellen und löschen
- Tabellen und Ansichten umbenennen, verschieben und löschen
- Tabellen samt Struktur in eine andere ClickHouse-Verbindung kopieren
- Die Datenbank der Verbindung sichern und wiederherstellen
- Daten und Struktur in der SQL-Konsole ändern, eine Änderung pro Ausführung

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach:

- **Host** und **Port** der HTTP-Schnittstelle: 8123 oder 8443 mit TLS. Der
  native Port 9000 ist nicht gemeint;
- **TLS**: HTTPS mit Prüfung des Serverzertifikats. ClickHouse Cloud benötigt es;
- **Authentifizierung**: Benutzername und Passwort oder ein Benutzer ohne
  Passwort. Ohne andere Angabe ist der Benutzer `default`;
- **Datenbank**: der Ort, an dem der Katalog geöffnet wird. Das Feld kann leer
  bleiben. Alle Datenbanken, die der Benutzer sehen darf, erscheinen trotzdem.

Eine Verbindungszeichenfolge wie `clickhouse://ann@ch.example.com:8123/logs`,
die in **URL** eingefügt wird, füllt diese Felder aus. Auch
`https://ch.example.com:8443` wird erkannt, und `?secure=true` aktiviert TLS.
Ein Passwort in der eingefügten Zeichenfolge wird in das Passwortfeld
übernommen und aus der Zeichenfolge entfernt.

Unterstützt wird ClickHouse ab Version 23.8. Ein älterer Server wird beim
Prüfen der Verbindung mit Angabe seiner Version abgelehnt. Ein Benutzer mit dem
Profil `readonly = 1` kann nicht verwendet werden: Jede Leseanfrage übermittelt
eigene Einstellungen, was diesem Benutzer möglicherweise nicht erlaubt ist.

## Der Katalog

- Die erste Ebene besteht aus Datenbanken. Die in der Verbindung angegebene
  steht an erster Stelle; `system` und `information_schema` gehören zum Server
  und sind entsprechend gekennzeichnet.
- Eine Datenbank enthält ihre Tabellen, Ansichten und materialisierten
  Ansichten. Die Tabelle, in der eine materialisierte Ansicht ihre Zeilen
  speichert, wird nicht daneben aufgeführt: Sie wird über die Ansicht gelesen.
- Für MergeTree-Tabellen zeigt der Server, wie viele Zeilen und welche Größe
  eine Tabelle hat. Andere Engines liefern diese Angaben nicht.

## Zeilen lesen

- Zahlen werden exakt wie gespeichert angezeigt, bis zur letzten Stelle von
  `UInt256` oder `Decimal`.
- Jeder Zeitpunkt wird unabhängig von der Zeitzone der Spalte in UTC mit `Z`
  angezeigt. Auch ein Filterwert ohne Zeitzonenversatz wird als UTC gelesen.
- Arrays, Maps und Tupel werden als JSON angezeigt.
- Textspalten mit Bytes, die kein UTF-8 sind, zeigen Ersatzzeichen.
- In ClickHouse ist kein Schlüssel eindeutig. Deshalb wird eine Tabellenseite
  nach dem Sortierschlüssel und danach nach allen übrigen Spalten geordnet: Die
  nächste Seite wiederholt die letzte Zeile nicht. Tabellen, deren Engine Daten
  von außen liest — etwa aus einer URL, Datei oder einem Stream — oder die nie
  enden, wie `system.numbers`, folgen der Reihenfolge der Engine.

## Zeilen ändern

- In einer MergeTree-Tabelle können Zellen bearbeitet, Blöcke eingefügt sowie
  Zeilen eingefügt und gelöscht werden. Log-, TinyLog-, StripeLog-, Memory-,
  Buffer- und Distributed-Tabellen nehmen nur eingefügte Zeilen an. Ansichten,
  Tabellen mit externen Daten und die eigenen Tabellen des Servers nehmen
  nichts an.
- ClickHouse hat keinen Schlüssel, der Zeilen unterscheidet. Eine Zeile wird
  daher anhand all ihrer Werte gefunden. Zeilen, deren Werte vollständig
  übereinstimmen, sind für Leser dieselbe Zeile: Wird eine bearbeitet, ändern
  sich alle; wird eine gelöscht, werden alle gelöscht. Die Anzahl danach zeigt,
  wie viele entfernt wurden.
- Eine Zeile, die sich von einer anderen nur in einer Gleitkomma-, Map- oder
  JSON-Spalte unterscheidet, lässt sich nicht von ihr unterscheiden und wird
  nicht geändert. Der Grund wird angezeigt.
- Wurde eine Zeile nach dem Lesen von jemand anderem geändert, wird Ihre
  Änderung abgelehnt statt sie zu überschreiben. Lesen Sie die Seite erneut und
  wiederholen Sie die Änderung. Eine Änderung im selben Moment wird nicht
  erkannt: ClickHouse hat keine Transaktion, die die Zeile festhält.
- Spalten des Sortier-, Primär- oder Partitionsschlüssels, berechnete Spalten,
  Maps und JSON-Spalten werden nicht bearbeitet. ClickHouse legt anhand des
  Schlüssels fest, wo eine Zeile gespeichert wird, und kann sie nicht
  verschieben.
- Der Server liest einen Wert als Typ seiner Spalte und lehnt ihn ab, wenn er
  nicht passt. Ein Einfügeblock wird ganz oder gar nicht übernommen; unpassende
  Zellen werden markiert. Zeitpunkte werden wie angezeigt in UTC gelesen;
  Arrays und Tupel werden als das JSON geschrieben, als das sie angezeigt
  werden.
- Eine Tabelle mit `enable_block_number_column` und
  `enable_block_offset_column` wird mit einem leichtgewichtigen `UPDATE`
  geändert. Jede andere Tabelle wird durch eine Mutation geändert, die die
  betroffenen Teile neu schreibt: geeignet für wenige Zeilen, langsam bei
  Hunderten eingefügten Zeilen.
- Eine neue Zeile hat erst nach erneutem Lesen der Seite einen Zeilenbezug und
  kann daher nicht sofort bearbeitet werden.

## Struktur ändern

- Spalten einer MergeTree-Tabelle können hinzugefügt, umbenannt und gelöscht,
  mit einem Standardwert versehen, als erforderlich oder optional festgelegt
  und im Typ geändert werden. Überspringindizes können erstellt und gelöscht
  werden. Andere Engines und Ansichten werden nicht geändert.
- Spalten des Sortier-, Primär- oder Partitionsschlüssels können weder gelöscht
  noch umbenannt oder geändert werden: ClickHouse legt anhand des Schlüssels
  fest, wo eine Zeile gespeichert wird.
- Vor einem Typwechsel zählt der Server die Werte, die der neue Typ nicht
  aufnehmen kann. Bevor eine Spalte verpflichtend wird, zählt er die Zeilen
  ohne Wert. Solange eine der Zahlen größer als null ist, wird nichts geändert:
  ClickHouse konvertiert die Zeilen erst nach dem Spaltenwechsel, und eine
  fehlgeschlagene Konvertierung würde die Tabelle unlesbar machen. Scheitert
  sie dennoch, wird sie gestoppt und der alte Typ wiederhergestellt. Ein Wert,
  bei dem etwas verloren ginge — `1.5` in einer Ganzzahl — zählt als nicht
  darstellbar.
- Ein Typwechsel schreibt die ganze Tabelle auf dem Datenträger neu. Die Dauer
  hängt daher von ihrer Größe ab.
- Ein Überspringindex ist Min/Max, eine Menge von bis zu hundert Werten oder ein
  Bloom-Filter für ausgewählte Spalten. Er wird auch über bereits vorhandene
  Zeilen erstellt. Kein solcher Index ist eindeutig; der Primärschlüssel kann
  nicht gelöscht werden.
- ClickHouse bietet keine eindeutigen Schlüssel und Fremdschlüssel, die hier
  erstellt werden könnten.

## Eine Tabelle erstellen

- **Tabelle erstellen** auf einer Datenbank öffnet den Tabellenentwurf. Vor
  der Ausführung wird ein einzelnes `CREATE TABLE` für eine MergeTree-Tabelle
  als Plan angezeigt.
- Der Primärschlüssel wird zum Sortierschlüssel der Tabelle: ClickHouse hält
  Zeilen in dieser Reihenfolge und findet sie darüber, verhindert aber nicht,
  dass mehrere Zeilen denselben Schlüssel haben. Schlüsselspalten müssen einen
  Wert enthalten. Ohne Schlüssel werden Zeilen in Eingangsreihenfolge gehalten.
- Eine Spalte, die leer sein darf, ist `Nullable`; eine Array- oder JSON-Spalte
  enthält immer einen Wert. Berechnete Spalten werden beim Schreiben der Zeile
  berechnet.
- Jetzt, heute und eine zufällige UUID können einen Standardwert oder eine
  berechnete Spalte füllen.
- Eindeutige Schlüssel, Fremdschlüssel, Identitätsspalten, Sortierungen und
  Partitionen nach Bereich, Liste oder Hash gibt es in ClickHouse nicht. Der
  Entwurf weist beim betreffenden Objekt darauf hin.
- Eine aus Tabellenzeilen erstellte Tabelle ist eine MergeTree-Tabelle, deren
  Spalten alle leer sein dürfen. Werden ihre Zeilen abgelehnt, bleibt die
  Tabelle nicht bestehen.

## Der Abschnitt System

- Nach den Datenbanken enthält **System** Angaben des Servers über sich selbst:
  **Prozesse**, **Mutationen**, **Zusammenführungen**, **Tabellengrößen**,
  **Datenträger**, **Geänderte Einstellungen**, **Metriken** und **Benutzer**.
  Sie lassen sich wie Tabellen sortieren, filtern und seitenweise lesen.
  Prozesse, Mutationen, Zusammenführungen und Metriken werden alle paar
  Sekunden erneut gelesen.
- Wählen Sie unter **Prozesse** Abfragen aus und klicken Sie auf **Abfrage
  abbrechen**, um sie zu stoppen. Was eine Abfrage bereits geschrieben hat,
  bleibt bestehen.
- Unter **Mutationen** beendet **Mutation stoppen** eine Änderung, die
  Tabellenteile neu schreibt. Eine wiederholt fehlschlagende Mutation blockiert
  alle späteren Änderungen ihrer Tabelle. Der Fehler steht in der letzten
  Spalte; nach dem Stoppen kann die Tabelle wieder geändert werden.
- Die gesamte Datenbank `system` ist ebenfalls im Katalog verfügbar und enthält
  alles, was diese Berichte auslassen.

## Suche und Download

- Das Suchfeld findet Datenbanken und Tabellen nach Namen sowie Tabellen nach
  Spaltennamen, Spaltenkommentar oder Tabellenkommentar. `%` und `_` sind
  gewöhnliche Zeichen.
- **Herunterladen** exportiert alle Zeilen, die zu den Filtern und der
  Sortierung der Seite passen, nicht nur die aktuelle Seite.

## Katalogaktionen

- **Neue Datenbank** auf der obersten Ebene der Verbindung.
- Für eine Datenbank: **Tabelle erstellen**, **Aus CSV laden**,
  **Datenbank löschen** und **Als Code modellieren**. Eine Datenbank wird erst
  gelöscht, nachdem Sie ihren Inhalt gesehen und bestätigt haben, alles darin
  zu löschen.
- Für eine Tabelle oder Ansicht: **Umbenennen**, **In Datenbank verschieben**,
  **Löschen** und **Als Code modellieren**. Vor dem Löschen werden
  materialisierte Ansichten genannt, die die Tabelle lesen und danach nicht
  mehr funktionieren würden. Gewöhnliche Ansichten werden nicht genannt: Der
  Server führt keine Liste der von einer Ansicht gelesenen Tabellen.
- Eine CSV-Datei wird zu einer Tabelle, deren Spalten alle Text enthalten und
  leer sein dürfen.
- Der Server verweigert das Löschen einer Tabelle, die seine eigene Grenze
  überschreitet: 50 GB, sofern der Administrator sie nicht geändert hat. Der
  Grund wird angezeigt.
- Hier lässt sich nichts rückgängig machen: ClickHouse speichert jede Änderung
  sofort.

## Tabellen kopieren

**Kopieren** Sie Tabellen im Katalog und **fügen** Sie sie in eine Datenbank
einer anderen ClickHouse-Verbindung oder dieser Verbindung ein. Sie kommen mit
Spalten, Standardwerten, berechneten Spalten, Codecs und Kommentaren,
Überspringindizes, Prüfungen, Engine, Schlüsseln und Einstellungen an. Das
Fenster fragt dasselbe wie bei PostgreSQL, zeigt alle Anweisungen und führt vor
**Kopieren** nichts aus.

- Tabellen der MergeTree-Familie sowie die Engines Log und Memory werden
  kopiert. Replizierte Tabellen, Ansichten und Tabellen über Dateien, URLs,
  Streams oder andere Server werden nicht kopiert; das Fenster nennt den Grund.
- Materialisierte Ansichten, die eine kopierte Tabelle lesen, bleiben zurück
  und werden im Fenster genannt.
- Zuerst werden die Tabellen erstellt, dann folgen die Zeilen. Scheitert oder
  stoppt der Kopiervorgang, werden die von ihm erstellten Tabellen wieder
  gelöscht.
- Während des Lesens werden die Tabellen nicht gesperrt: Zeilen, die
  zwischendurch geschrieben werden, können mitkopiert werden oder fehlen.

In eine andere Verbindungsart eingefügte Zeilen werden wie Zeilen jeder anderen
Tabelle übertragen.

## Sicherungen

**Sicherungen** im Aktionsmenü des Katalogs funktionieren wie bei PostgreSQL
für die Datenbank, die in der Verbindung angegeben ist. Eine Verbindung ohne
angegebene Datenbank kann nicht gesichert werden.

- Die Sicherung ist eine Textdatei mit der Anweisung für jede Tabelle, Ansicht
  und materialisierte Ansicht sowie den Zeilen jeder Tabelle. Tabellen anderer
  Engines, etwa replizierte, werden in der Datei als ausgelassen aufgeführt.
- Die Tabellen werden nacheinander gelesen, nicht zum selben Zeitpunkt.
- **Wiederherstellen** löscht und erstellt jede in der Sicherung enthaltene
  Tabelle und Ansicht neu. Was die Datenbank enthält, aber nicht in der
  Sicherung steht, bleibt erhalten. Die Wiederherstellung ist nur in einer
  Datenbank gleichen Namens und mit derselben oder einer neueren ClickHouse-
  Version möglich.

## Dashboards

Eine ClickHouse-Verbindung kann Daten an Dashboards melden. Das Layout heißt
**ClickHouse-Server**: Verbindungen und laufende Abfragen, Abfragen pro
Sekunde, gelesene, eingefügte und zusammengeführte Zeilen, Arbeitsspeicher,
Netzwerkverkehr, aktive Teile, fehlgeschlagene Abfragen und Größe der
Datenbank dieser Verbindung. Die Zähler gelten für den ganzen Server.

## Ein eigener Server

**Neue Verbindung** bietet **ClickHouse hier starten**: Ein Server wird auf
diesem Rechner gestartet und als Verbindung gespeichert, die sich mit seinem
Benutzer `default` anmeldet. Dieser Benutzer darf auch Benutzer und Rechte
verwalten. Mit Beispieldaten wird `demo_lab` geöffnet — Organisationen,
Personen, Projekte und ihre Aufgaben sowie zweihunderttausend Seitenaufrufe —
mit Beispielen für jeden Bildschirm: Partitionen, TTL, Codecs und
Überspringindizes, ReplacingMergeTree und SummingMergeTree, zwei von den
Seitenaufrufen gespeiste materialisierte Ansichten, eine Ansicht und eine
Log-Tabelle.

## SQL-Konsole

**Neue Abfrage** unter **Abfragen** in der linken Leiste startet eine Abfrage
für die Verbindung. **Als Abfrage öffnen** über einer Tabelle startet eine
Abfrage für diese Tabelle. Die Konsole funktioniert wie die PostgreSQL-Konsole
— Lesen, Änderungen, **Erklären**, Vervollständigung und Formatierung — mit
diesen Unterschieden:

- Die über dem Editor ausgewählte Datenbank ist die Standarddatenbank; es kann
  jeweils nur eine sein.
- Es gibt keine Transaktion im Modus **Manuell**, und nichts wird zunächst
  ausprobiert: ClickHouse speichert jede Änderung sofort und kann sie nicht
  zurücknehmen. Deshalb wird jede Anweisung, die etwas einfügt, löscht, ändert
  oder erstellt, einzeln ausgeführt. Ein Änderungsskript wird Anweisung für
  Anweisung ausgeführt; Leseabfragen können gemeinsam laufen.
- Eine Leseabfrage läuft mit der Servereinstellung `readonly`, die Schreibzugriffe
  serverseitig verhindert.
- `ALTER TABLE … DELETE` und `UPDATE` werden vor Ende der Anweisung
  abgeschlossen, sodass die nächste Leseabfrage die geänderten Zeilen bereits
  sieht.
- Parameter werden im ClickHouse-Format `{name:Type}` geschrieben. Der Server
  liest den Wert als diesen Typ und lehnt unpassende Werte ab; **SQL-NULL**
  sendet NULL an einen `Nullable`-Typ. Der Wert wird so gelesen wie bei
  `--param_` von clickhouse-client; ein Backslash beginnt also eine
  Escape-Sequenz.
- `INSERT INTO t FORMAT JSONEachRow` mit den Zeilen danach funktioniert ebenso
  wie `SHOW`, `DESCRIBE`, `EXISTS`, `CHECK TABLE` und `EXPLAIN AST`, `SYNTAX`,
  `PIPELINE` und `ESTIMATE`. Ein einfaches `EXPLAIN` ist **Erklären**.
- Nicht unterstützt sind `SET` und `USE` — setzen Sie stattdessen `SETTINGS` in
  der Anweisung und wählen Sie die Datenbank über dem Editor — sowie `SYSTEM`,
  `DETACH`, `ATTACH`, Benutzer, Rollen, Rechte, Funktionen und ein `FORMAT` bei
  `SELECT`, da die Konsole das Ergebnis selbst anzeigt.
- **Stoppen** und das Zeitlimit beenden eine Anweisung mit `KILL QUERY`.
