# Dateien

Ihr persönlicher Speicher auf diesem Server: ein eigener Ordner, auf den niemand
sonst zugreift, es sei denn, Sie teilen eine Verbindung dorthin. Sie durchsuchen
Ordner, öffnen Dateien im Viewer, der zu ihnen passt, bearbeiten sie und bewegen
Dateien hinein und hinaus. Wie Verbindungen im Allgemeinen funktionieren, steht
auf der Seite [Verbindungen](connections.md).

## Was Sie sehen können

- Ordner und Dateien und was jedes davon ist: Größe, Daten, Format
- Tabellen in CSV-, TSV-, Excel- und Parquet-Dateien sowie in Logs
- Dokumente, Code, Bilder, PDFs, Aufzeichnungen und das Innere von zip-Archiven
- Dateien, die nach Namen oder nach dem Text in ihnen gefunden werden
- SQL, das über in Dateien gehaltene Tabellen läuft

## Was Sie ändern können

- Dateien in einem Texteditor
- Die Zeilen und Spalten von CSV- und TSV-Dateien
- Dateien und Ordner: erstellen, hochladen, umbenennen, löschen, herunterladen
- Archive: Dateien in eines packen oder eines entpacken
- Dateien, die zwischen Ordnern und Verbindungen kopiert oder verschoben werden

## Verbinden

Das einzige Feld ist **Pfad**: der Ordner in Ihrem persönlichen Speicher, auf dem
die Verbindung sich öffnet. `/` ist die Wurzel Ihres Speichers, `/reports/2026`
ein Ordner darin. Nichts außerhalb Ihres Speichers ist erreichbar.

**Ordner verbinden**, im Aktionsmenü des Katalogs auf einem Ordner, erstellt eine
neue Verbindung, die sich auf diesem Ordner öffnet.

Eine SQLite-Datenbankdatei (`.db`, `.db3`, `.sqlite`, `.sqlite3`) öffnet sich
als Liste ihrer Tabellen und Ansichten, mit ungefähr der Zeilenzahl jeder.
**Als SQLite verbinden**, über dieser Liste oder im Aktionsmenü der Datei,
erstellt eine neue SQLite-Verbindung zu ihr. Nur eine Datei in Ihrem
persönlichen Speicher lässt sich verbinden; anderswo ist die Aktion
ausgegraut und nennt den Grund.

## Der Katalog

- Der Pfad der Ebene, auf der Sie sich befinden, wird oben gezeigt. **Pfad
  dieser Ebene kopieren** kopiert ihn in der Form, die das Feld **Pfad** annimmt.
- **Die Wurzel dieser Verbindung** kehrt dorthin zurück, wo die Verbindung sich
  öffnet.
- Das Filterfeld verengt die Ebene nach Namen.
- Die Suchschaltfläche daneben sucht dieselben Wörter in jedem Ordner darunter,
  nach Namen. Halten Sie **Shift** gedrückt, während Sie sie drücken, um
  stattdessen in den Dateien zu suchen; beim ersten Mal sagt sie, was das kostet,
  und fragt nach. Ein Treffer zeigt die Zeile, in der er gefunden wurde.
  **Zurück zum Ordner** verlässt die Ergebnisse.
- Das Drücken einer Datei öffnet sie in einem Tab. Das Drücken eines Ordners,
  einer Arbeitsmappe oder eines zip-Archivs geht in ihn hinein.
- **Details**, im Aktionsmenü, sagen, was eine Datei oder ein Ordner ist: seine
  Größe, seine Daten, seine Berechtigungen, als was er geöffnet werden kann und
  was sein Format über sich selbst sagt (die Spalten einer Parquet-Datei, die
  Blätter einer Arbeitsmappe, die Länge einer Aufzeichnung, die Größe eines
  Bildes).

## Dateien öffnen

Eine Datei öffnet sich im Viewer, der zu ihr passt. Wo es mehr als eine
Möglichkeit gibt, sie zu öffnen, werden die anderen über ihr angeboten.

- **CSV und TSV** öffnen sich als Tabellen. Jede Spalte ist Text.
- **Excel-Arbeitsmappen** (`.xlsx`, `.xlsm`) öffnen sich auf ihrem ersten
  sichtbaren Blatt. Die anderen Blätter liegen am Fuß der Tabelle, wo eine
  Tabellenkalkulation sie hat. Formeln zeigen den zuletzt in der Datei
  gespeicherten Wert.
- **Parquet** öffnet sich als Tabelle mit den Spaltentypen, die die Datei
  angibt.
- **JSON** und **JSON lines** öffnen sich als Text, und **Als Tabelle anzeigen**
  macht Zeilen daraus.
- **Logs** (`.log`) öffnen sich als Text, und **Als Tabelle anzeigen** teilt jede
  Zeile in ihre Zeit, Stufe und Nachricht.
- **Markdown** öffnet sich als Dokument, mit Inhaltsverzeichnis, Code, Formeln,
  Diagrammen und Grafiken. **Exportieren** speichert es als HTML-Seite oder
  druckt es.
- **Text und Code** öffnen sich im Editor mit Hervorhebung.
- **Bilder**, **PDF**, **Audio** und **Video** öffnen sich in ihren eigenen
  Viewern. Ein PDF kann durchsucht werden.
- In ein **zip-Archiv** wird wie in einen Ordner hineingegangen, und die Dateien
  darin öffnen sich wie jede andere, schreibgeschützt.

Tabellen aus Dateien werden in der Datentabelle wie jede andere gelesen (für die
Datentabelle selbst siehe [PostgreSQL](source-postgres.md)), mit zwei
Unterschieden: eine Datei kann nicht sortiert werden, und ein Filter passt nur
genau auf einen Wert.

## Bearbeiten

- Eine Text-, JSON-, JSON-lines- oder Markdown-Datei öffnet sich im Editor.
  **Speichern** schreibt sie zurück. Eine JSON-Datei muss weiterhin gültig sein,
  um gespeichert zu werden.
- Wenn die Datei sich geändert hat, seit Sie sie geöffnet haben, wird das
  Speichern abgelehnt und nichts geschrieben. **Datei neu laden** liest sie
  erneut.
- Dateien bis 4 MB können bearbeitet werden. Eine größere Datei öffnet sich
  schreibgeschützt und sagt, warum.
- In einer CSV- oder TSV-Tabelle können Sie Zellen ändern, Zeilen einfügen,
  angehakte Zeilen löschen und Spalten über **Struktur** hinzufügen, umbenennen
  oder verwerfen.

## Dateien und Ordner

Das Aktionsmenü des Katalogs bietet auf der Ebene, auf der Sie sich befinden,
oder für das Angehakte:

- **Neuer Ordner**, **Neue Datei**, **Dateien hochladen**. Ein Upload sagt, was
  bei einem bereits vergebenen Namen zu tun ist: abbrechen, die Datei ersetzen
  oder beide unter einem neuen Namen behalten;
- **Umbenennen**, **Löschen**. Es gibt keinen Papierkorb: eine gelöschte Datei
  ist weg;
- **Herunterladen**: eine Datei so, wie sie ist; einen Ordner oder mehrere
  angehakte Dateien als ein zip;
- **Archivieren**: das Angehakte in ein zip, tar, tar.gz, tar.bz2 oder tar.xz
  packen;
- **Entpacken**: ein Archiv hier oder in einen eigenen Ordner entpacken;
- **Kopieren** und **Ausschneiden**, dann **Einfügen**, wo Sie sie haben
  möchten. Das funktioniert zwischen Ordnern einer Verbindung und zwischen
  Verbindungen, einschließlich SSH-Servern. Das Einfügen einer Tabelle aus einer
  Datenbank in einen Ordner speichert sie als CSV-Datei.

Ein Kopieren zwischen Verbindungen läuft im Hintergrund. Die Aktivitätsglocke
zeigt, wie es vorangeht, und kann es anhalten.

## SQL über Dateien

**Als Abfrage öffnen** über einer Tabelle oder **Neue Abfrage** unter
**Abfragen** auf der linken Leiste startet eine SQL-Konsole auf dieser
Verbindung. Eine Tabelle wird durch ihren Pfad in doppelten Anführungszeichen
benannt, etwa `SELECT * FROM "sales/2026.csv"`. CSV-, TSV-, Parquet-, JSON-,
JSON-lines- und Log-Dateien können abgefragt und verbunden werden;
Excel-Blätter noch nicht. Nichts, was eine Abfrage tut, wird in die Dateien
zurückgeschrieben.

## Grenzen

- Der Editor hält Dateien bis 4 MB.
- Eine Suche in Dateien überspringt Dateien über 8 MB und hört nach dem Lesen
  von 256 MB auf.
- Ein Ordner listet höchstens 2000 Einträge.
- Eine Datei in einem Archiv wird bis 32 MB gelesen.
- Ein Download oder ein Archiv hält höchstens 10.000 Dateien und 2 GB.
