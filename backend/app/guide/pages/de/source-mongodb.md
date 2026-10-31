# MongoDB

Ein MongoDB-Server. Sie durchsuchen seine Datenbanken und Collections und
lesen Dokumente seitenweise als Zeilen; die Felder einer Collection werden aus
ihren Dokumenten ermittelt. Wie Verbindungen allgemein funktionieren, erfahren
Sie auf der Seite [Verbindungen](connections.md).

## Was Sie sehen können

- Datenbanken, Collections, Views und Zeitreihen
- Dokumente als Zeilen, sortiert und gefiltert vom Server
- Die Felder der Dokumente einer Collection und ihre Indizes
- Die Definition einer Collection: Optionen, Validator und Indizes als JSON
- Jedes Dokument vollständig als JSON, seitenweise
- Wie viele Dokumente eine Collection enthält und wie viel Platz sie belegt
- mongosh, angemeldet wie die Verbindung, in einem Terminal
- Alle passenden Dokumente, als Datei heruntergeladen
- Operationen, Verbindungen, Benutzer und Rollen des Servers
- Die Zähler des Servers auf einem Dashboard

## Was Sie ändern können

- Dokumente: Felder bearbeiten, Blöcke einfügen, Dokumente hinzufügen und löschen
- Ein Feld in jedem Dokument: hinzufügen, löschen, umbenennen, Typ ändern
- Indizes: normal und eindeutig, Hash, Text und georäumlich
- Datenbanken und Collections: anlegen, umbenennen, verschieben, löschen, CSV
- Eine laufende Operation: aus ihrem Bericht stoppen
- Collections samt Indizes in eine andere MongoDB-Verbindung kopieren
- Die Datenbank der Verbindung: in eine Datei sichern und daraus wiederherstellen
- Alles, was mongosh ändern kann, in seinem Terminal

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach:

- **Host** und **Port** eines Servers, 27017, sofern er nicht anderswo lauscht;
- **TLS**: einer verschlüsselten Verbindung mit Prüfung des Serverzertifikats;
- **Authentifizierung**: Benutzer und Passwort oder keine, für einen Server
  ohne Zugriffskontrolle. Die **Authentifizierungsdatenbank** ist die, in der
  der Benutzer angelegt wurde, `admin`, sofern nicht in einer anderen;
- **Datenbank**: wo der Katalog öffnet. Sie darf leer bleiben. Jede Datenbank,
  die der Benutzer sehen darf, steht so oder so im Katalog.

Eine Verbindungszeichenfolge wie `mongodb://ann@db.example.com:27017/shop`,
eingefügt in **URL**, füllt diese Felder; `?authSource=` und `?tls=true`
werden ebenfalls gelesen. Ein Passwort darin wandert ins Passwortfeld und
verlässt die Zeichenfolge.

Der genannte Server ist der, mit dem gesprochen wird. Ein Mitglied eines
Replica Sets wird gelesen, wie es ist; um Daten zu ändern, nennen Sie den
Primary. Eine `mongodb+srv://`-Adresse und eine Liste von Servern werden nicht
unterstützt.

MongoDB 5.0 und neuer wird unterstützt. Ein älterer Server wird bei der
Verbindungsprüfung mit Nennung seiner Version abgelehnt.

## Der Katalog

- Die erste Ebene sind die Datenbanken. Die in der Verbindung genannte kommt
  zuerst, auch bevor etwas in ihr gespeichert ist; `admin`, `local` und
  `config` gehören dem Server und sind so markiert.
- In einer Datenbank liegen ihre Collections und Views. Eine Collection zeigt,
  wie viele Dokumente sie enthält und wie viel Platz sie auf der Festplatte
  belegt.

## Dokumente als Zeilen

- Die Spalten einer Collection sind die Felder ihrer Dokumente: die ihr
  Validator deklariert, dann die in den ersten und letzten hundert Dokumenten
  gefundenen. `_id` kommt zuerst. Ein Feld, das nur in einem anderen Dokument
  vorkommt, wird auf dessen Seite gezeigt und kann nicht sortiert oder
  gefiltert werden.
- Jede Spalte nennt den Typ, den ihre Dokumente enthalten: Text, Zahl, Datum,
  ObjectId, Objekt, Array. Ein Feld, bei dem die Dokumente uneins sind, ist
  gemischt.
- Eine ObjectId wird hexadezimal gezeigt, ein Datum in UTC mit `Z`, ein
  Decimal mit allen Stellen. Objekte und Arrays erscheinen als JSON in der
  Form, die `mongosh` schreibt; ebenso jeder Wert ohne einfache Schreibweise.
- Ein fehlendes Feld und ein Feld mit null zeigen beide eine leere Zelle und
  passen beide zu **ist leer**.
- Ein Filterwert wird gelesen, wie das Feld Werte hält: eine Zahl als Zahl,
  ein Datum als Zeitpunkt, eine ObjectId über ihr Hex. Text, der wie eine
  Abfrage aussieht, ist nur Text.
- Eine Seite ohne eigene Sortierung ist nach `_id` geordnet, sodass die
  nächste Seite die letzte nie wiederholt.
- Ein Feld, dessen Name einen Punkt enthält oder mit `$` beginnt, wird gezeigt,
  kann aber nicht sortiert oder gefiltert werden.

## Dokumente ändern

- Eine Zelle ist ein Feld eines Dokuments. Was Sie eingeben, wird gespeichert,
  wie das Feld Werte hält; ein Objekt oder Array als JSON in der Form, die die
  Zelle zeigt. Ein gemischtes Feld nimmt JSON, wenn die Eingabe JSON ist, sonst
  Text.
- Ein Dokument, das seit dem Lesen der Seite geändert wurde, wird nicht
  überschrieben: Sie erfahren es, und die Seite wird neu gelesen.
- `_id` kann nicht geändert werden. Eine geleerte Zelle speichert null.
- Ein neues Dokument enthält nur die ausgefüllten Felder; bleibt `_id` leer,
  wird eine erzeugt.
- Ein eingefügter Block wird zuerst ganz geprüft und dann Dokument für
  Dokument geschrieben. Ein Block neuer Dokumente kommt ganz oder gar nicht.
- Views, Zeitreihen und die Collections des Servers werden hier nicht
  geändert; eine Zeitreihe nimmt neue Dokumente auf.
- **Als Dokumente anzeigen** zeigt jedes Dokument vollständig, jede Ebene.

## Struktur

Die Spalten einer Collection sind die Felder ihrer Dokumente, daher ändert der
Strukturbildschirm alle Dokumente auf einmal: **Hinzufügen** setzt das neue
Feld auf null, wo es fehlt; **Löschen** und **Umbenennen** wirken in jedem
Dokument; **Typ ändern** konvertiert jeden Wert mit der Konvertierung des
Servers und ändert nichts, wenn ein Wert sich nicht konvertieren lässt. Ein
eindeutiger Index wird nicht angelegt, wenn sich Werte wiederholen. Views,
Zeitreihen und die Collections des Servers behalten ihre Struktur; ein
Validator wird in mongosh geändert.

## Katalogaktionen und der Abschnitt Server

- **Neue Datenbank** fragt auch nach der ersten Collection: MongoDB behält
  eine Datenbank nur, solange sie etwas enthält.
- Eine Collection wird umbenannt, samt Dokumenten und Indizes in eine andere
  Datenbank verschoben oder gelöscht. Eine View kann nur gelöscht werden.
- **Aus CSV laden** macht aus den Zeilen einer Datei eine Collection; jeder
  Wert ist Text, ein leerer ist kein Feld.
- Der Abschnitt **Server** nach den Datenbanken enthält Operationen,
  Verbindungen, Benutzer und Rollen. **Operation stoppen** stoppt das in
  Operationen Gewählte.
- Die Suche findet Datenbanken, Collections und Berichte nach Namen.

## Kopien, Sicherungen und ein eigener Server

- **Tabellen kopieren** kopiert Collections mit Optionen, Validator, jedem
  Dokument und den Indizes in eine Datenbank einer MongoDB-Verbindung.
- Eine Sicherung ist das Archiv von `mongodump`; eine Wiederherstellung
  schreibt es mit `mongorestore` über diese Datenbank. Nicht über einen
  SSH-Tunnel.
- **Dienste** kann ein eigenes MongoDB starten und es mit der Datenbank
  `demo_lab` füllen.

## mongosh

**Terminal öffnen** auf einer eigenen MongoDB-Verbindung startet `mongosh`,
angemeldet wie die Verbindung und in ihrer Datenbank. Es läuft in einem
Container, den dieser Server dafür startet, und nur dort, wo er Container
starten darf; nicht über einen SSH-Tunnel. Das Schließen des Terminals oder
`exit` beendet es.
