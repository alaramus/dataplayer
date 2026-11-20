# FTP

Ein über FTP oder FTPS erreichbarer Server. Sie durchsuchen seine Ordner ab
einer gewählten Stelle und arbeiten mit seinen Dateien wie mit Ihren eigenen:
Tabellen, SQL über Dateien, Ansichten und Suche. Die Anmeldung erfolgt mit
Passwort oder anonym. Wie Verbindungen allgemein funktionieren, steht auf der
Seite [Verbindungen](connections.md).

## Was Sie sehen können

- Ordner und Dateien unterhalb des gewählten Ordners
- Tabellen in CSV-, TSV-, Excel- und Parquet-Dateien sowie in Logs
- Dokumente, Code, Bilder, PDFs, Aufnahmen und den Inhalt von ZIP-Archiven
- Dateien, gefunden nach Namen oder nach dem Text darin
- SQL über Tabellen in Dateien

## Was Sie ändern können

- Dateien in einem Texteditor
- Die Zeilen und Spalten von CSV- und TSV-Dateien
- Dateien und Ordner: anlegen, hochladen, umbenennen, löschen, herunterladen
- Archive: Dateien in eines packen oder eines entpacken
- Dateien, kopiert oder verschoben zwischen Ordnern und Verbindungen

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach:

- **Host** und **Port**: 21, oder 990 für implizites TLS;
- **Verschlüsselung**: **TLS, explizit** sprechen heute die meisten Server, auf
  Port 21. **TLS, implizit** ist das ältere FTPS auf Port 990. **Keine
  Verschlüsselung** sendet das Passwort so, wie Sie es eingeben: wählen Sie es
  nur für einen Server, der nichts anderes anbietet;
- **Zertifikat prüfen**: nur für einen Server mit selbst erstelltem Zertifikat
  ausschalten;
- **Ordner**: wo das Durchsuchen beginnt. Leer ist der Ordner, in den der
  Server Sie bei der Anmeldung bringt, `/` die oberste Ebene des Servers;
- **Authentifizierung**: **Benutzer** und **Passwort**, oder **Anonym** für
  einen öffentlichen Server.

**URL** zeigt den Server als `ftp://user@host/folder`, für implizites TLS als
`ftps://`. Eine dort eingefügte Adresse füllt Host, Port, Benutzer und Ordner.
Das Passwort ist nie Teil davon.

## Der Katalog und die Dateien

Eine FTP-Verbindung wird wie eine [Dateien](source-file.md)-Verbindung
durchsucht: derselbe Katalog, dieselbe Suche nach Namen und in Dateien,
dieselben Ansichten und dasselbe SQL über Dateien. Auch dieselben Aktionen: **Neuer Ordner**, **Neue Datei**,
**Dateien hochladen**, **Umbenennen**, **Löschen**, **Download**, **Archivieren**,
**Entpacken**, **Kopieren**, **Ausschneiden** und **Einfügen**.

Worin sich ein FTP-Server von einer Festplatte unterscheidet:

- Was Sie lesen und ändern dürfen, entscheiden die Rechte des Servers selbst.
- Eine Datei, deren Name nicht in UTF-8 ist, wird nicht angezeigt. Sie bleibt
  auf dem Server.
- Manche Server nennen Zeiten nur auf die Minute, bei älteren Dateien nur den
  Tag, und keiner nennt seine Zeitzone: Zeiten werden in UTC angezeigt.
- Eine Datei über 200 MB wird nicht als Tabelle, Arbeitsmappe, Archiv oder in
  SQL geöffnet: laden Sie sie herunter. Text, Bilder, PDFs und Aufnahmen
  öffnen sich in jeder Größe.
- Eine Suche in Dateien überspringt Dateien über 1 MB und hört nach insgesamt
  32 MB auf, weil jedes Byte über das Netz geht.
- Kopieren leitet jedes Byte durch DataPlayer, weil FTP kein eigenes Kopieren
  kennt: bis zu 200 MB auf einmal.
- Eine Datei, die über eine inzwischen geänderte gespeichert wird, wird
  abgelehnt statt überschrieben.
