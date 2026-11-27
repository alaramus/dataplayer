# S3

Amazon S3 oder ein Speicher, der dessen API spricht. Sie durchsuchen Buckets und
Ordner und arbeiten mit Objekten wie mit Ihren eigenen Dateien: Tabellen, SQL
über Dateien, die Ansichten und die Suche. Die Anmeldung erfolgt mit einem
Zugriffsschlüssel. Wie Verbindungen allgemein funktionieren, steht auf der Seite
[Verbindungen](connections.md).

## Was Sie sehen können

- Buckets und die Ordner und Objekte darin
- Tabellen in CSV-, TSV-, Excel- und Parquet-Dateien sowie in Protokollen
- Dokumente, Code, Bilder, PDFs, Aufnahmen und den Inhalt von ZIP-Archiven
- Objekte, gefunden nach Namen oder nach dem Text darin
- SQL über Tabellen, die in Objekten liegen

## Was Sie ändern können

- Objekte in einem Texteditor
- Die Zeilen und Spalten von CSV- und TSV-Dateien
- Objekte und Ordner: anlegen, hochladen, umbenennen, löschen, herunterladen
- Archive: Objekte in eines packen oder eines entpacken
- Objekte, kopiert oder verschoben zwischen Ordnern und Verbindungen
- Buckets: einen anlegen oder einen mit seinem Inhalt löschen

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach:

- **Endpunkt**: der Adresse des Speichers, etwa `https://s3.example.com`. Leer
  ist Amazon S3;
- **Region**: aus der Liste gewählt, die Amazon liefert, oder getippt, sobald
  ein Endpunkt einen anderen Speicher nennt; leer ist `us-east-1`;
- **Zugriffsschlüssel** und **Geheimer Schlüssel**;
- **Bucket**: leer zeigt jeden Bucket, den der Schlüssel auflisten darf;
- **Ordner**: wo das Durchsuchen im Bucket beginnt;
- **Adressierung**: „auto“ ist virtual-hosted bei Amazon S3 und path-style
  anderswo, was jeder kompatible Speicher annimmt;
- **Zertifikat prüfen**: nur ausschalten für einen Speicher, dessen Zertifikat
  Sie selbst ausgestellt haben.

**AWS-Konto** meldet sich statt mit einem Schlüssel über eines Ihrer [Cloud-Konten](cloud-accounts.md) an: ein Sitzungstoken, eine übernommene Rolle oder die Anmeldedaten dieses Servers gehören zum Konto.

**URL** zeigt, wo der Speicher ist: seinen Endpunkt oder die Adresse von
Amazon S3 in der Region. Eine dort eingefügte Adresse füllt den Endpunkt, eine
Amazon-S3-URL auch die Region; `s3://reports/2026` füllt Bucket und Ordner.
Bucket und Ordner werden in der URL nicht wiederholt, und die Schlüssel sind
nie Teil davon.

Der Katalog der Typen zeigt für jeden Anbieter eine Karte: Amazon S3, MinIO,
RustFS, Cloudflare R2, Backblaze B2, Wasabi, DigitalOcean Spaces, Google Cloud
Storage, Yandex Object Storage, VK Cloud, Selectel und Hetzner Object Storage.
Jede Karte ist dieses eine Formular: Sie füllt aus, was der Anbieter immer
gleich nennt, und sagt, wo der Rest steht. Keine startet einen Server.

## Der Katalog und die Objekte

Eine S3-Verbindung wird wie eine [Dateien](source-file.md)-Verbindung
durchsucht: derselbe Katalog, dieselbe Suche nach Namen und in Dateien,
dieselben Ansichten und dasselbe SQL über Dateien. Auch dieselben Aktionen: **Neuer Ordner**, **Neue Datei**,
**Dateien hochladen**, **Umbenennen**, **Löschen**, **Download**, **Archivieren**,
**Entpacken**, **Kopieren**, **Ausschneiden** und **Einfügen**.

Worin sich ein Speicher von einer Festplatte unterscheidet:

- Ein Ordner ist der gemeinsame Anfang von Schlüsseln, `reports/2026/`. Ein
  leerer Ordner ist ein leeres Objekt, dessen Schlüssel auf `/` endet; so legen
  ihn auch die Konsolen der Anbieter an.
- Ein Schlüssel, der kein Dateiname sein könnte — mit einem leeren Teil, `.`
  oder `..`, einem Backslash oder einem Laufwerk wie `C:` —, wird nicht
  angezeigt. Im Bucket bleibt er.
- Ein Objekt über 200 MB wird nicht als Tabelle, Arbeitsmappe, Archiv oder in
  SQL geöffnet: Laden Sie es herunter. Text, Bilder, PDFs und Aufnahmen öffnen
  sich in jeder Größe.
- Eine Suche in Objekten überspringt solche über 1 MB und hört nach insgesamt
  32 MB auf, weil jedes Byte über das Netz geht.
- Ein Objekt in einer Archiv-Speicherklasse muss erst wiederhergestellt werden,
  bevor es gelesen werden kann.
- Einen Ordner umzubenennen oder zu verschieben kopiert jedes Objekt darin und
  entfernt die alten: Der Speicher kann nicht umbenennen. Bis zu 10.000
  Objekte werden auf einmal verschoben, kopiert oder gelöscht; ein größerer
  Ordner wird abgelehnt.
- Eine Datei, die sich inzwischen geändert hat, wird nicht überschrieben: Das
  Speichern wird abgelehnt.

### Buckets

Ist **Bucket** leer, listet die oberste Ebene des Katalogs die Buckets.

- **Neuer Bucket** legt dort einen Bucket in der Region der Verbindung an. Sein
  Name hat 3 bis 63 Kleinbuchstaben, Ziffern, Punkte und Bindestriche und
  beginnt und endet mit einem Buchstaben oder einer Ziffer.
- **Löschen** entfernt einen Bucket mit allem darin, bis zu 10.000 Objekte. Ein
  Bucket, der alte Versionen seiner Objekte aufbewahrt, wird abgelehnt: Leeren
  Sie ihn zuerst mit einer Lebenszyklusregel.
- Ein Bucket kann nicht umbenannt werden: Der Speicher kennt diese Operation
  nicht. Einen Bucket **kopieren** oder **ausschneiden** und in einen Ordner
  eines anderen Buckets **einfügen** legt seine Objekte dort in einen Ordner
  seines Namens; ein ausgeschnittener Bucket wird gelöscht, sobald er leer ist.
- Oben liegen nur Buckets, daher werden neue Datei, Hochladen und Einfügen dort
  nicht angeboten. Ein Bucket hat ein eigenes Symbol.
