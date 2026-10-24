# PostgreSQL

Eine relationale Datenbank. Sie durchsuchen ihre Schemas, lesen Tabellen Seite
für Seite, bearbeiten Zeilen und Struktur, führen SQL in einer Konsole aus und
kopieren Daten hinein und hinaus. Wie Verbindungen im Allgemeinen funktionieren,
steht auf der Seite [Verbindungen](connections.md).

## Was Sie sehen können

- Schemas, Tabellen und Ansichten, ihre Zeilen sortiert und gefiltert
- Die Spalten einer Tabelle, ihre Schlüssel und die Tabellen, auf die sie
  verweist
- Jede passende Zeile, heruntergeladen als Datei
- Was der Server tut: Prozesse, Einstellungen, Rollen, Erweiterungen
- Servermetriken auf Dashboards

## Was Sie ändern können

- Tabellendaten und Spalten
- Tabellen und Schemas: erstellen, umbenennen, verschieben, verwerfen
- Eine in eine Tabelle geladene CSV-Datei
- Rollen
- Eine Sicherung der ganzen Datenbank
- TimescaleDB-Hypertabellen, Kompression und Aufbewahrung, wenn es installiert
  ist

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach:

- **Host** und **Port**, 5432, wenn der Server nichts anderes sagt;
- **Authentifizierung**: ein Benutzer und ein Passwort oder kein Passwort für
  einen Server, der der Adresse vertraut, von der Sie sich verbinden;
- **Datenbank**, **Benutzer** und **Passwort**.

Eine Verbindungszeichenfolge wie `postgresql://ann@db.example.com:5432/sales`, in
**URL** eingefügt, füllt diese Felder. Ein Passwort in der eingefügten
Zeichenfolge wandert in das Passwortfeld und verlässt die Zeichenfolge.

## Der Katalog

Das Drücken der Verbindung öffnet ihren Katalog.

- Die Schema-Steuerung oben wählt, welche Schemas aufgelistet werden. Mehrere
  können zusammen aufgelistet werden; die Liste sagt dann, zu welchem Schema
  jede Zeile gehört. Die Wahl wird in diesem Browser gemerkt.
- Zeilen sind Tabellen, partitionierte Tabellen, Ansichten und materialisierte
  Ansichten. Das Drücken einer öffnet ihre Zeilen in einem Tab.
- Das Filterfeld verengt die Ebene nach Namen.
- **System** ist ein Abschnitt von Berichten, die der Server über sich selbst
  gibt (siehe **Berichte** unten).
- Das Anhaken von Relationen und das Wählen von **Beziehungen** im Aktionsmenü
  zeichnet sie und die Schlüssel zwischen ihnen als Diagramm.
- **Details** sagen, wie eine Relation gespeichert ist, wem sie gehört, wie
  viele Spalten, Indizes und Einschränkungen sie hat, wie groß sie auf der
  Platte ist und wann der Server sie zuletzt gemessen hat.

Tabellen in den Schemas `pg_` und in `information_schema` gehören dem Server.
Sie werden wie jede andere Tabelle gelesen und werden von hier aus nie geändert.

## Zeilen lesen

Eine Tabelle öffnet sich als Datentabelle, Seite für Seite. Die Befehlszeile
darüber ist in fünf Gruppen geteilt: **Die Ansicht**, **Lesen als**, **Ausgeben**,
**Die Zeilen ändern** und **Dieser Tab**. Ein Befehl, der hier nicht verwendet
werden kann, bleibt an seinem Platz, ausgegraut, und sagt bei Zeigen darauf,
warum.

- **Sortieren**: der Pfeil im Kopf einer Spalte. Mehrere Spalten können zusammen
  sortiert werden, der Reihe nach.
- **Filter**: Bedingungen für Spalten, durch AND verbunden. Was eine Spalte
  anbietet, hängt von ihrem Typ ab: Vergleiche für Zahlen, Daten und Text;
  „enthält“ und „beginnt mit“ für Text; Gleichheit und „einer aus einer Liste“
  für Boolesche Werte, UUIDs und Enums; „leer“ oder „nicht leer“ für jede Spalte.
- **Spalten**: eine Spalte links anheften, sie ausblenden, die Reihenfolge
  ändern, an ihrem Rand ziehen, um sie zu verbreitern, auf den Rand
  doppelklicken, um sie anzupassen.
- **Pro Seite**, neben dem Blätterer am Fuß: bis zu 500 Zeilen.
- **Automatisch aktualisieren** liest die Seite alle 1 s bis 5 min erneut. Es
  wartet, solange eine Zelle bearbeitet wird oder Zeilen angehakt sind.
- Eine Zelle, deren Spalte Teil eines Fremdschlüssels ist, hat einen Pfeil. Das
  Drücken zeigt, wohin er führt, und die Wahl dessen öffnet die Zeile, auf die
  er zeigt.
- **Was auf diese Zeile zeigt** listet die Tabellen auf, deren Schlüssel hierher
  zeigen, und öffnet die passenden Zeilen in ihnen.
- **Diese Zeile nach unten lesen**, in der Ecke einer Zeile, zeigt eine Zeile als
  Spalte von Namen und Werten. Seine Pfeile gehen zur nächsten und vorherigen
  Zeile.
- Ein JSON- oder Array-Wert öffnet sich bei Doppelklick ganz in einem Viewer;
  Shift + Doppelklick bearbeitet ihn. **Den vollen Wert kopieren** kopiert ihn.
- Das Anhaken von Zellen und Drücken von Ctrl+C kopiert sie als
  tabulatorgetrennten Text.

Die Filter, die Sortierung und die Spalten einer Tabelle werden in diesem
Browser gemerkt.

## Die Struktur einer Tabelle

**Struktur** öffnet die Spalten, Schlüssel, Indizes und Einschränkungen der
Tabelle neben ihren Zeilen.

Mit Zugriff auf **Struktur ändern** können Sie:

- eine Spalte hinzufügen, umbenennen, verwerfen oder ihren Typ ändern;
- ihren Standardwert setzen oder verwerfen und leere Werte erlauben oder
  verbieten. Vor dem Verbieten werden die leeren Zeilen gezählt, und wenn es
  welche gibt, wird abgebrochen;
- einen Index hinzufügen oder verwerfen;
- einen eindeutigen Schlüssel oder einen Fremdschlüssel hinzufügen oder
  verwerfen.

**DDL anzeigen**, über den Zeilen, zeigt das SQL, das die Tabelle erneut
erstellen würde. **Als Code modellieren**, im Aktionsmenü des Katalogs, schreibt
ein Schema oder eine Tabelle als SQLAlchemy-Modell, Django-Modell oder
DBML-Dokument und lädt es herunter.

## Zeilen bearbeiten

Mit Zugriff auf **Zeilen bearbeiten**:

- doppelklicken Sie auf eine Zelle, um sie zu ändern. **SQL NULL setzen**
  speichert einen leeren Wert, der nicht dasselbe ist wie leerer Text;
- **Zeile einfügen** fügt eine Zeile am Ende der Seite hinzu. Spalten mit einem
  Standardwert können unberührt bleiben;
- haken Sie ganze Zeilen an und drücken Sie **Ausgewählte Zeilen löschen**. Alle
  werden gelöscht oder keine;
- fügen Sie einen Block kopierter Zellen mit **In die Auswahl einfügen** in eine
  Auswahl ein. Zuerst wird jeder Wert gegen den Typ seiner Spalte geprüft, und
  wenn einer scheitert, wird nichts geschrieben.

Wenn jemand eine Zeile geändert hat, nachdem Sie sie gelesen haben, wird Ihre
Änderung abgelehnt, statt über die andere geschrieben. Laden Sie neu und
versuchen Sie es erneut.

Zeilen können nur aus einer Tabelle mit einem Primärschlüssel gelöscht werden.
Ansichten sind schreibgeschützt.

## Tabellen und Schemas

Das Aktionsmenü des Katalogs bietet auf einem Schema oder für angehakte
Relationen:

- **Neues Schema**, **Schema umbenennen**, **Schema verwerfen**;
- **Tabelle erstellen**: die Spalten, Schlüssel und Indizes entwerfen, das SQL
  prüfen, das ausgeführt wird, und sie dann erstellen;
- **Umbenennen**, **In Schema verschieben**, **Verwerfen**. Mehrere Relationen
  auf einmal zu verwerfen ist ein Schritt: alle gehen oder keine.

Was ein Verwerfen mitnimmt, wird gezeigt, bevor Sie bestätigen.

## Daten hineinbringen und hinausnehmen

- **Aus CSV laden** auf einem Schema: eine CSV-Datei hochladen und eine Tabelle
  daraus machen.
- **Zeilen hineinbringen** über einer Tabelle: eine Tabelle in einer beliebigen
  Verbindung wählen, ihre Spalten mit denen dieser Tabelle paaren, eine Vorschau
  ansehen und die Zeilen hineinkopieren.
- **Diese Zeilen als neue Tabelle oder Datei behalten** kopiert die Zeilen auf
  dem Bildschirm in eine neue Tabelle in einer anderen Verbindung oder in eine
  CSV-Datei in einem Ordner.
- **Herunterladen** fragt nach **Aktuelle Seite** oder **Alle passenden Zeilen**
  und ob die Datei heruntergeladen oder **In meinen Dateien speichern** werden
  soll.
- **Kopieren** Sie Tabellen im Katalog und **Fügen** Sie sie in ein Schema einer
  anderen PostgreSQL-Verbindung **ein**: sie werden mit ihren Spalten, Schlüsseln
  und Indizes kopiert. Ob die Fremdschlüssel zwischen ihnen mitkommen, wird
  gefragt.
- Das Einfügen kopierter Tabellen in einen Ordner einer Datei- oder
  SSH-Verbindung speichert jede als CSV-Datei.

Lange Kopien laufen im Hintergrund. Die Aktivitätsglocke zeigt, wie sie
vorangehen, und kann sie anhalten.

## Die SQL-Konsole

**Abfragen** auf der linken Leiste listet Ihre gespeicherten Abfragen auf und
startet eine **Neue Abfrage** auf einer Verbindung. **Als Abfrage öffnen** über
einer Tabelle startet eine auf dieser Tabelle.

- **Ausführen** führt die Auswahl oder die Anweisung unter dem Cursor aus.
  **Skript ausführen** führt den ganzen Text aus.
- Ergebnisse werden unter dem Editor gezeigt und können geblättert, gefiltert,
  sortiert, heruntergeladen und diagrammiert werden.
- **Plan** zeigt den Plan einer Anweisung, ohne sie auszuführen.
- Änderungen werden sofort festgeschrieben, wenn nicht **Manuell** eingeschaltet
  ist. Dann hält die Konsole eine Transaktion offen, bis **Festschreiben** oder
  **Zurückrollen**.
- Die Einstellung **Konsolen** der Verbindung entscheidet, ob Änderungen erlaubt,
  jedes Mal erfragt oder abgelehnt werden.
- Das Ändern der Struktur (Tabellen, Ansichten, Indizes, Schemas) wird immer
  erfragt. Eine zerstörende Änderung wird zuerst innerhalb einer Transaktion
  versucht, und Ihnen wird gezeigt, was sie bewirken würde.
- Der Editor vervollständigt Schema-, Tabellen- und Spaltennamen.
- Jede Ausführung wird im Verlauf der Abfrage behalten.

## Berichte

**System** im Katalog enthält sechs Berichte über den Server. Sie werden wie
Tabellen gelesen und können sortiert, gefiltert, heruntergeladen und diagrammiert
werden.

- **Prozesse**: was verbunden ist und was jede Verbindung tut. Jede Zeile hat
  **Abfrage abbrechen** und **Beenden**. Der Bericht liest sich alle fünf Sekunden
  selbst neu.
- **Parameter**: die Konfiguration des Servers.
- **Tablespaces**, **Routinen**.
- **Rollen**: die Benutzer des Servers. **Neue Rolle** über den Zeilen erstellt
  eine. Nur der Eigentümer der Verbindung hat sie.
- **Erweiterungen**: was installiert werden kann und was installiert ist. Jede
  Zeile hat **Installieren** oder **Entfernen**.

## Sicherungen

**Sicherungen**, im Aktionsmenü des Katalogs, listet die Sicherungen dieser
Datenbank auf, die in Ihrem persönlichen Speicher behalten werden.

- **Diese Datenbank herauskopieren** erstellt eine neue. Sie läuft im
  Hintergrund.
- **Wiederherstellen** legt eine in diese Datenbank zurück. Es ersetzt die
  Objekte, die die Sicherung enthält, und fragt zuerst nach.
- **Diese Sicherung löschen** entfernt eine.

Nur der Eigentümer der Verbindung kann sie sichern. Die Schaltfläche ist
ausgegraut, wenn diese Installation das Sicherungsprogramm nicht ausführen kann.

## TimescaleDB

Wenn die Datenbank die TimescaleDB-Erweiterung hat, sind Hypertabellen und
kontinuierliche Aggregate im Katalog markiert, und das Aktionsmenü einer
Hypertabelle bietet:

- **Chunk-Intervall ändern**, **Kompression konfigurieren**;
- **Aufbewahrungsrichtlinie setzen**, **Kompressionsrichtlinie setzen**,
  **Aktualisierungsrichtlinie setzen** und das Entfernen jeder von ihnen;
- **Chunks komprimieren**, **Chunks dekomprimieren**;
- **In Hypertable umwandeln**, auf einer gewöhnlichen Tabelle.

Arbeit, die viele Chunks berührt, wird zuerst geplant und vor der Ausführung zur
Prüfung gezeigt. Danach läuft sie im Hintergrund, und die Aktivitätsglocke zeigt,
wie weit sie gekommen ist und was mit jedem Chunk geschehen ist.

## Metriken

Eine PostgreSQL-Verbindung kann ihre eigenen Zähler an Dashboards melden:
Sitzungen nach Zustand, Transaktionen, gelesene und geschriebene Zeilen, von der
Platte und aus dem Speicher gelesene Blöcke, Konflikte, Deadlocks und die Größe
der Datenbank. Der Eigentümer schaltet dies im Fenster **Quellen** des Bereichs
**Dashboards** ein und wählt, wie oft. Das fertige Layout dafür heißt
**PostgreSQL-Datenbank**.

## Grenzen

- Eine Seite mit Zeilen hält höchstens 500 Zeilen.
- Ein eingefügter Block ist höchstens 500 Zeilen und 2000 Zellen.
- Das Löschen wirkt auf die Zeilen der Seite, auf der Sie sich befinden.
- Filter werden durch AND verbunden. OR gibt es nicht.
