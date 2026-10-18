# Verbindungen

Eine Verbindung ist ein gespeicherter Weg zu einer Quelle: eine
PostgreSQL-Datenbank, ein Redis-Server, ein Ordner mit eigenen Dateien oder ein
Server über SSH. Kataloge, Tabellen, Abfragekonsolen, Pipelines und Dashboards
arbeiten alle über Verbindungen.

Jede Art von Quelle hat ihre eigene Seite: [Dateien](source-file.md),
[PostgreSQL](source-postgres.md), [Redis](source-redis.md) und
[SSH](source-ssh.md).

## Die Liste der Verbindungen

Die Spalte **Verbindungen** befindet sich links im Bereich **Daten**. Der
Bereich **Pipelines** zeigt dieselbe Liste.

- Drücken Sie auf den Namen einer Verbindung, um ihren Katalog zu öffnen. Er
  öffnet sich in der Spalte neben der Liste, als Tab, der nach der Verbindung
  benannt ist.
- Drücken Sie auf das Symbol einer Verbindung, um ihr Fenster zu öffnen, in dem
  sie bearbeitet wird.
- **+** am Kopf der Spalte fügt eine Verbindung hinzu.
- Die Lupe macht aus dem Kopf einen Filter nach Namen. **Esc** oder das Kreuz
  schließt ihn.
- Der Pfeil am Ende des Kopfes liest die Liste erneut.
- Die Schaltfläche oben links auf dem Bildschirm verengt die Spalte zu Symbolen
  und erweitert sie wieder. Die schmale Spalte öffnet weiterhin Kataloge und hat
  weiterhin **+**.

Ein Punkt auf jedem Symbol sagt, was die letzte Prüfung ergeben hat:

- grün: die Quelle hat geantwortet;
- rot: die Quelle hat nicht geantwortet oder hat abgelehnt;
- gelb: die Verbindung ist ausgeschaltet;
- grau: sie wurde noch nicht geprüft.

Verbindungen werden geprüft, solange der Arbeitsbereich geöffnet ist. Wie oft,
wird auf der Seite **Einstellungen** festgelegt.

## Eine Verbindung hinzufügen

1. Drücken Sie **+** am Kopf von **Verbindungen**. Das Fenster **Neue
   Verbindung** öffnet sich.
2. Wählen Sie eine Art von Quelle. Die Arten sind links gruppiert: **SQL-
   Datenbanken**, **Schlüssel-Wert-Speicher**, **Dateien und Speicher**. Das
   Suchfeld findet eine Art nach ihrem Namen oder nach dem, was sie kann.
3. Der Bereich rechts sagt, was die Art ist, was Sie durch sie sehen und ändern
   können, und enthält **Handbuch**, das ihre Seite dieses Handbuchs öffnet.
4. Drücken Sie **Verbindung erstellen** oder doppelklicken Sie auf die Art. Das
   Verbindungsfenster öffnet sich dafür.
5. Füllen Sie die Felder aus, drücken Sie **Verbindung testen**, dann **OK**, um
   zu speichern und zu schließen, oder **Anwenden**, um zu speichern und das
   Fenster offen zu lassen. **Zurück** kehrt ohne Speichern zur Liste der Arten
   zurück.

Wo dieser Server Container ausführen kann, bietet der Bereich außerdem an, einen
neuen Server dieser Art auf dieser Maschine zu starten: **PostgreSQL hier
starten**, **TimescaleDB hier starten**, **Redis hier starten** oder **SSH-
Server hier starten**. Das sich öffnende Fenster fragt **Wie**:

- automatisch: der Server wird für Sie benannt, erhält ein Passwort, das niemand
  wählen muss, und wird mit Beispieldaten gefüllt, damit es etwas zu sehen gibt;
- mit eigenen Entscheidungen: ein Name, ein Benutzer, eine Datenbank, ein Port
  auf dieser Maschine und bei einem SSH-Server, ob Sie sich mit einem Passwort
  oder mit einem Ihrer SSH-Schlüssel anmelden.

So oder so wird die Verbindung für Sie erstellt. Wie der Start verläuft, zeigt
die Aktivitätsglocke unten rechts. Wenn der Server bereit ist, zeigt ein Fenster,
wie Sie ihn von Ihren eigenen Werkzeugen aus erreichen, und sein Passwort, ein
einziges Mal. Kopieren Sie das Passwort dann, wenn Sie es anderswo brauchen.

Eine ausgegraute Schaltfläche sagt bei Zeigen darauf, warum: diese Installation
darf vielleicht überhaupt keine Container ausführen.

## Das Verbindungsfenster

Das Fenster einer Verbindung öffnet sich, wenn Sie eine hinzufügen oder auf ihr
Symbol drücken. Es können mehrere gleichzeitig offen sein, sodass Sie eine
Verbindung lesen können, während Sie eine andere ausfüllen. Das Schließen eines
Fensters mit ungespeicherten Änderungen fragt zuerst nach.

- **Name** ist, wie die Verbindung aufgelistet wird. Er ist erforderlich.
- **Tab-Farbe** färbt die Tabs der Verbindung und ihre Zeile in der Liste.
- **In Verwendung** schaltet die Verbindung aus, ohne sie zu löschen. Eine
  ausgeschaltete Verbindung behält ihre Einstellungen, lässt sich nicht öffnen
  und hat einen gelben Punkt.
- **URL** ist die aus den Feldern zusammengesetzte Verbindungszeichenfolge. Das
  Passwort ist nie Teil davon. Fügen Sie eine Verbindungszeichenfolge ein, und
  die Felder werden daraus gefüllt. Die Schaltfläche zum Kopieren daneben kopiert
  die Zeichenfolge.
- **Verbindung testen** versucht mit dem zu verbinden, was das Formular gerade
  enthält, gespeichert oder nicht. Die Antwort erscheint in einem kleinen
  Popup über der Schaltfläche.
- **Löschen** entfernt die Verbindung. Nur ihr Eigentümer hat die Schaltfläche,
  und sie fragt zuerst nach.

Das Fenster hat mindestens drei Seiten.

### Verbindung

Wie die Quelle zu erreichen ist. Die Felder hängen von der Art der Quelle ab und
sind auf ihrer Seite beschrieben. Eine Auswahl unter **Authentifizierung**
ändert, welche Felder gezeigt werden.

### Optionen

**Antworten behalten** legt fest, wie lange eine Katalogebene und eine Seite mit
Zeilen wiederverwendet werden dürfen, bevor die Quelle erneut gelesen wird.

- **Wie diese Quelle entscheidet** ist die Standardeinstellung. Die Beschriftung
  sagt, wie lange das ist.
- **Antworten nie behalten** liest die Quelle jedes Mal.
- **Behalten für …** legt eine eigene Zeit fest, bis zu einem Tag.

Das Drücken einer Neu laden-Schaltfläche liest immer die Quelle, was auch immer
hier gewählt ist. Eine kleine Markierung neben der Neu laden-Schaltfläche sagt
**Live**, solange die Antwort auf dem Bildschirm frisch von der Quelle kommt,
und zeigt eine Uhr, sobald sie eine behaltene ist. Zeigen Sie darauf, um zu
sehen, wie alt sie ist.

Eine Quelle, die nichts behält, sagt es, und das Feld ist ausgeschaltet.

### Berechtigungen

- **Konsolen** legt fest, was eine Abfragekonsole über diese Verbindung tun
  darf: **Nur lesen**, **Vor dem Schreiben fragen** (die Standardeinstellung)
  oder **Schreiben erlaubt**. Es gilt für alle, mit denen die Verbindung
  geteilt wird.
- **Erlauben, Daten an Dritte zu senden** legt fest, ob über diese Verbindung
  gelesene Daten an einen externen Dienst gesendet werden dürfen, etwa an einen
  Anbieter von AI-Modellen. Es ist aus, solange Sie es nicht einschalten.
- **Wer sonst darf darauf zugreifen** listet die Personen auf, mit denen die
  Verbindung geteilt wird, und die Anfragen, die auf eine Antwort warten.
  **Teilen** gibt sie jemandem.

## Eine Verbindung teilen

Eine Verbindung gehört der Person, die sie erstellt hat. Der Eigentümer kann
anderen Personen eine von drei Stufen geben:

- **Lesen**: den Katalog öffnen, Zeilen lesen, sie herunterladen und
  diagrammieren;
- **Zeilen bearbeiten**: auch Zeilen ändern, hinzufügen und löschen;
- **Struktur ändern**: auch Spalten, Indizes, Schlüssel und Tabellen ändern.

Eine Stufe gilt für die ganze Verbindung, nicht für eine einzelne Tabelle. Nur
der Eigentümer kann die Verbindung löschen, ihre Einstellungen ändern, sie
sichern oder weiter teilen.

Eine geteilte Verbindung erscheint in der Liste der anderen Person. Ihr Fenster
zeigt, wer sie geteilt hat und auf welcher Stufe, und ihre Felder lassen sich
nicht ändern.

Eine Tabelle kann auch als Link geteilt werden: **Diese Ansicht teilen** in der
Befehlszeile über einer Tabelle erstellt einen Link auf diese Tabelle mit ihren
Filtern und Spalten. Ein Link gibt für sich genommen keinen Zugriff. Wer ihn
ohne Zugriff auf die Verbindung öffnet, kann ihn anfragen, und die Anfrage
erscheint auf der Seite **Berechtigungen** des Eigentümers und in seiner
Aktivitätsglocke. Der Eigentümer wählt die Stufe, wenn er sie genehmigt.

## Einen Katalog öffnen

Das Drücken einer Verbindung öffnet ihren Katalog: was die Quelle enthält, Ebene
für Ebene oder als Baum, je nach Art der Quelle. Ein Katalog hat oben eine
eigene Befehlszeile und ein Menü mit Aktionen für das Angehakte. Die Befehle
hängen von der Art der Quelle ab und sind auf ihrer Seite beschrieben.

Dinge, die in jedem Katalog erscheinen:

- das Anhaken eines Knotens und das Öffnen des Aktionsmenüs wirkt auf das
  Angehakte oder, wenn nichts angehakt ist, auf die Ebene, auf der Sie sich
  befinden;
- **Details** sagt, was ein Knoten ist: seine Größe, seine Daten, als was er
  geöffnet werden kann;
- **Kopieren** und **Ausschneiden** nehmen Knoten auf, und **Einfügen** legt sie
  dort ab, wo Sie stehen, in derselben Verbindung oder in einer anderen;
- das Öffnen eines Knotens öffnet ihn in einem eigenen Tab in der Arbeitsspalte,
  als Zeilen, als Dokument, als Bild und so weiter;
- der Katalog kann neben sich selbst dupliziert oder mit dem Katalog einer
  anderen Verbindung in einem Fenster gepaart werden, um Dinge zwischen den
  beiden zu verschieben.
