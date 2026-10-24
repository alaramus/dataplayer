# Redis

Ein Schlüssel-Wert-Server im Arbeitsspeicher. Sie durchlaufen seine Schlüssel als
Baum aus den Doppelpunkten in ihren Namen, lesen, was ein Schlüssel enthält, als
Zeilen, schreiben Schlüssel jedes Typs und setzen oder löschen ihre Ablaufzeit.
Wie Verbindungen im Allgemeinen funktionieren, steht auf der Seite
[Verbindungen](connections.md).

## Was Sie sehen können

- Jede Datenbank auf dem Server und ihre Schlüssel als Baum
- Was ein Schlüssel enthält, als Zeilen: Felder, Elemente, Punkte, Einträge
- Den Typ eines Schlüssels, seine Größe und die verbleibende Lebensdauer
- Einen Ordner aus Hashes als eine Tabelle
- Servermetriken auf Dashboards

## Was Sie ändern können

- Die Werte in einem Schlüssel, einen nach dem anderen
- Schlüssel aller sechs Typen: erstellen, ersetzen, löschen
- Die Ablaufzeit eines Schlüssels: setzen oder entfernen
- Tabellen, die über Ordnern aus Hashes beschrieben werden
- Schlüssel, die als CSV-Dateien gespeichert werden

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach:

- **Host** und **Port**, 6379, wenn der Server nichts anderes sagt;
- **Datenbank**: die, auf der der Katalog sich öffnet. Jede Datenbank bleibt vom
  Katalog aus erreichbar;
- **Authentifizierung**: ein Passwort oder keines.

Eine Verbindungszeichenfolge wie `redis://:secret@cache.example.com:6379/0`, in
**URL** eingefügt, füllt diese Felder. Eine `rediss://`-Adresse, die TLS braucht,
wird noch nicht unterstützt.

## Der Katalog

Der Katalog ist ein Baum.

- Die Steuerung oben wählt die Datenbank. Sie sagt, wie viele Schlüssel jede
  enthält. Die Wahl wird in diesem Browser gemerkt.
- Schlüssel werden nach den Doppelpunkten in ihren Namen gruppiert:
  `session:42:token` liegt unter `session`, dann unter `42`. Das Drücken eines
  Ordners öffnet ihn an seiner Stelle.
- Ein Schlüssel sagt seinen Typ, seine Größe und, wenn er abläuft, wie lange er
  noch hat.
- Das Drücken eines Schlüssels öffnet ihn in einem Tab. Das Drücken einer Zeile
  wählt sie aus, und das Aktionsmenü wirkt dann auf sie.
- Ein sehr großer Schlüsselraum wird bis zu einer Obergrenze aufgelistet. Ein
  engerer Ordner zeigt, was darüber hinausgeht.

## Einen Schlüssel lesen

Ein Schlüssel öffnet sich als Zeilen. Die Form folgt seinem Typ:

- ein **string** ist ein Wert;
- ein **hash** sind Felder und Werte;
- eine **list** sind Positionen und Werte;
- ein **set** sind Mitglieder;
- ein **sorted set** sind Mitglieder und Punkte;
- ein **stream** sind Einträge.

Zeilen werden wie jede Tabelle in der Datentabelle geblättert. Redis hat keinen
Index über Werte, also kann nichts sortiert oder gefiltert werden.
**Herunterladen** kann jede Zeile als CSV-Datei speichern.

## Einen Schlüssel bearbeiten

Mit Zugriff auf **Zeilen bearbeiten** werden die Werte eines Schlüssels in seiner
Datentabelle bearbeitet:

- doppelklicken Sie auf eine Zelle, um ein hash-Feld, ein list-Element, einen
  string oder einen Punkt zu ändern;
- **Zeile einfügen** fügt ein Feld, ein Element, ein Mitglied hinzu;
- haken Sie Zeilen an, und **Ausgewählte Zeilen löschen** entfernt Felder und
  Mitglieder.

Was jeder Typ erlaubt, zeigt die Datentabelle selbst. Ein Element kann nicht aus
der Mitte einer list entfernt werden, und ein stream kann gar nicht bearbeitet
werden.

Wenn jemand den Wert geändert hat, nachdem Sie ihn gelesen haben, wird Ihre
Änderung abgelehnt, statt über die andere geschrieben. Laden Sie neu und
versuchen Sie es erneut.

## Schlüssel schreiben

Wählen Sie einen Ordner oder einen Schlüssel im Baum und öffnen Sie das
Aktionsmenü:

- **Neuer string**, **Neuer hash**, **Neue list**, **Neues set**,
  **Neues sorted set**, **Neuer stream**. Der eingegebene Name wird an den
  Ordner angehängt, in dem Sie stehen, deshalb wird `one`, in `cache:`
  geschrieben, zu `cache:one`. Eine Sammlung wird Zeile für Zeile mit einem
  Mitglied oder einem `name=value` geschrieben. Eine Ablaufzeit kann sofort
  gesetzt werden. Ein bereits verwendeter Name wird abgelehnt, es sei denn, Sie
  wählen, ihn zu ersetzen;
- **Löschen** entfernt einen Schlüssel, nachdem es gefragt hat;
- **Ablaufzeit setzen** gibt einem Schlüssel eine Lebensdauer, und
  **Ablaufzeit entfernen** nimmt sie weg.

## Hinauskopieren

**Kopieren** Sie einen Schlüssel, einen Ordner oder eine Datenbank im Katalog und
**Fügen** Sie ihn in einen Ordner einer Datei- oder SSH-Verbindung **ein**: jeder
wird zu einer CSV-Datei. Mehrere angehakte werden zusammen kopiert, je eine
Datei. Sie können auch alle Zeilen eines Schlüssels, Ordners oder einer Datenbank
als CSV exportieren.

## Metriken

Eine Redis-Verbindung kann ihre eigenen Zähler an Dashboards melden:
Arbeitsspeicher, Clients, Befehle, Treffer und Fehlschläge, abgelaufene und
verdrängte Schlüssel, Netzwerkverkehr und Schlüssel pro Datenbank. Der Eigentümer
schaltet dies im Fenster **Quellen** des Bereichs **Dashboards** ein und wählt,
wie oft. Das fertige Layout dafür heißt **Redis-Server**.

## Was Redis hier nicht hat

- Es gibt keine Befehlskonsole: Redis nimmt Befehle statt Anweisungen an, und
  eine Konsole dafür wäre eine Shell auf dem Server.
- Ein Schlüssel, der abläuft, während sein Tab geöffnet ist, bleibt auf dem
  Bildschirm, bis das Tab erneut gelesen wird.
- Werte werden als Text gezeigt. Ein Schlüssel, der ein Bild enthält, erscheint
  als unlesbare Zeichen.
