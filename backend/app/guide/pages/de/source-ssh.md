# SSH

Ein Server, den Sie über SSH erreichen. Sie durchsuchen seine Ordner und arbeiten
mit seinen Dateien wie mit Ihren eigenen: Tabellen, SQL über Dateien, der Editor,
Archive, Suche, Kopieren zwischen Verbindungen und ein Terminal. Er meldet sich
mit einem Passwort oder einem Ihrer SSH-Schlüssel an, und nur an dem Server,
dessen Schlüssel Sie bestätigt haben. Wie Verbindungen im Allgemeinen
funktionieren, steht auf der Seite [Verbindungen](connections.md).

## Was Sie sehen können

- Die Ordner und Dateien des Servers, von dort, wo Sie wählen
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
- Alles andere, aus einem Terminal auf dem Server

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach:

- **Host** und **Port**, 22, wenn der Server nichts anderes sagt;
- **Benutzer**: das Konto, mit dem Sie sich anmelden;
- **Ordner**: wo das Durchsuchen beginnt. Leer ist der Home-Ordner des Kontos;
- **Serverschlüssel**: womit der Server sich selbst beweist (siehe unten);
- **Authentifizierung**: ein Passwort oder **Schlüssel**, einer Ihrer
  SSH-Schlüssel.

Eine Verbindungszeichenfolge wie `ssh://ann@files.example.com:22`, in **URL**
eingefügt, füllt Host, Port und Benutzer. Ein Passwort ist nie Teil davon.

### Der Serverschlüssel

Nichts wird an einen Server gesendet, bis Sie seinen Schlüssel bestätigt haben.
Das ist es, was ein Passwort oder einen Schlüssel davon abhält, an eine Maschine
zu gehen, die nur vorgibt, Ihre zu sein.

1. Füllen Sie Host und Port aus und drücken Sie **Vom Server holen**.
2. Der Fingerabdruck des Servers wird gezeigt. Vergleichen Sie ihn mit dem, den
   der Administrator des Servers Ihnen gibt, oder mit dem, was `ssh-keyscan`
   ausgibt.
3. Drücken Sie **Diesem Schlüssel vertrauen**.

Ein Server, der später einen anderen Schlüssel vorzeigt, wird abgelehnt, mit
einem Satz, der das sagt. Wenn der Server neu installiert wurde, holen Sie seinen
Schlüssel erneut, vergleichen Sie und drücken Sie **Dem neuen Schlüssel
vertrauen**. Nur der Eigentümer der Verbindung kann das.

Ein Server, der über **SSH-Server hier starten** gestartet wurde, vertraut dem
Schlüssel, den er zuerst vorgezeigt hat, weil diese Anwendung ihn gestartet hat.

### SSH-Schlüssel

Ihre SSH-Schlüssel stehen auf der Seite **Einstellungen**, getrennt von
Verbindungen, damit ein Schlüssel so vielen Verbindungen dient, wie Sie ihn
verwenden lassen.

- **Neuer Schlüssel** erstellt einen Schlüssel auf diesem Server: ED25519 oder
  RSA für Server, die ED25519 ablehnen. **Importieren** nimmt einen privaten
  Schlüssel, den Sie einfügen oder als Datei auswählen.
- **Den öffentlichen Schlüssel kopieren** kopiert die Zeile, die in
  `~/.ssh/authorized_keys` auf dem Server hinzugefügt werden muss. Sie endet auf
  `dataplayer`, damit der Eigentümer des Servers erkennt, welche Zeile es ist.
- Die private Hälfte eines Schlüssels wird nie wieder jemandem gezeigt.
- Ein Schlüssel kann eine Passphrase haben, die auf eine von drei Weisen behalten
  wird: keine; neben dem Schlüssel gespeichert; oder abgefragt, wenn der
  Schlüssel gebraucht wird, und 15 Minuten, eine Stunde oder acht Stunden
  gehalten. **Jetzt sperren** vergisst sie früher.
- Ein gesperrter Schlüssel hält seine Verbindungen an. Jeder Bildschirm, der die
  Verbindung liest, bietet dann **Schlüssel entsperren** statt eines Fehlers.
- Ein Schlüssel, der von einer Verbindung verwendet wird, kann nicht gelöscht
  werden. Richten Sie die Verbindung zuerst auf einen anderen Schlüssel.

## Der Katalog und die Dateien

Eine SSH-Verbindung wird genau wie eine [Dateien](source-file.md)-Verbindung
durchsucht: derselbe Katalog, dieselbe Suche nach Namen und innerhalb von
Dateien, dieselben Viewer, derselbe Editor, dieselben Aktionen (**Neuer Ordner**,
**Neue Datei**, **Dateien hochladen**, **Umbenennen**, **Löschen**,
**Herunterladen**, **Archivieren**, **Entpacken**, **Kopieren**,
**Ausschneiden**, **Einfügen**) und dasselbe SQL über Dateien.

Nichts davon führt einen Befehl auf dem Server aus: alles geht über SFTP.

Unterschiede zu Ihren eigenen Dateien:

- **Ordner verbinden** wird nicht angeboten.
- Eine Datei größer als 200 MB wird nicht als Tabelle, Arbeitsmappe, Archiv oder
  in SQL geöffnet: laden Sie sie stattdessen herunter. Text, Bilder, PDFs und
  Aufzeichnungen öffnen sich unabhängig von ihrer Größe.
- Eine Suche in Dateien überspringt Dateien über 1 MB und hört nach insgesamt
  32 MB auf, weil jedes Byte über das Netz geht.

## Das Terminal

**Terminals** auf der linken Leiste öffnet ein Terminal im Bereich am Fuß des
Bildschirms: die Anmelde-Shell des Kontos der Verbindung, auf dem Server.

- Nur der Eigentümer der Verbindung kann eines öffnen. Personen, mit denen die
  Verbindung geteilt wird, können es nicht.
- Die Shell startet im Home-Ordner des Kontos, nicht im **Ordner** der
  Verbindung.
- Das Schließen des Terminals, das Schließen der Seite oder ein Netzausfall
  beenden die Shell. Sie wird nicht wieder verbunden; öffnen Sie eine andere.
- Mehrere Terminals können gleichzeitig offen sein, bis zu acht. Das Wechseln zu
  einem anderen Werkzeug im Bereich hält sie am Laufen.
