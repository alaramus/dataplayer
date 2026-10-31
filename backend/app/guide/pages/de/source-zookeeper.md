# ZooKeeper

Ein ZooKeeper-Server. Sie gehen seinen Znode-Baum durch, lesen die Daten eines
Znodes mit Stat und ACL, bearbeiten die Daten und blättern die Kinder eines
Znodes als Zeilen durch. Wie Verbindungen allgemein funktionieren, lesen Sie
auf der Seite [Verbindungen](connections.md).

## Was Sie sehen können

- Den Znode-Baum, dort aufgeklappt, wo Sie stehen
- Die Daten eines Znodes: JSON als Baum, Text als Text, alles andere als Hex
- Den Stat eines Znodes: Versionen, zxids, Kinder, Sitzung eines flüchtigen
- Die ACL eines Znodes: wer lesen, schreiben, anlegen, löschen, verwalten darf
- Die Kinder eines Znodes als Zeilen, seitenweise
- zkCli, verbunden mit Server und Wurzelpfad, in einem Terminal
- Die Berichte des Servers: Modus, Zähler, Clients, Watches, Einstellungen
- Die Zähler des Servers auf einem Dashboard
- Znodes, nach Namen gefunden
- Alle Kinder eines Znodes, als Datei heruntergeladen

## Was Sie ändern können

- Die Daten eines Znodes, ganz geschrieben, gegen die gelesene Version
- Neue Znodes, ganz oben oder in einem anderen, normal oder sequenziell
- Znodes löschen, einzeln oder mit allem darunter
- Die ACL eines Znodes und aller Znodes darunter
- Alles, was zkCli ändern kann, in seinem Terminal

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach:

- **Host** und **Port** eines Servers des Ensembles, 2181, wenn er nicht auf
  einem anderen lauscht;
- **Wurzelpfad**: Alles wird unter diesem Pfad gelesen, als wäre er die Spitze,
  und nichts darüber ist erreichbar. Leer lassen für den ganzen Baum;
- **TLS**: eine verschlüsselte Verbindung mit geprüftem Serverzertifikat;
- **Authentifizierung**: **Anonym** oder ein **Digest**-Benutzer mit Passwort,
  der beim Öffnen der Sitzung hinzugefügt wird.

Eine Verbindungszeichenfolge wie `zk.example.com:2181/apps/billing`, in **URL**
eingefügt, füllt diese Felder. Eine Liste von Servern wird nicht unterstützt:
Nennen Sie einen.

## Der Katalog

- Der Baum öffnet sich ganz oben oder am Wurzelpfad. Ein Znode mit Kindern hat
  einen Pfeil; ein Klick auf seinen Namen öffnet ihn.
- Jeder Znode zeigt, wie viele Daten er enthält, wie viele Kinder er hat und ob
  er flüchtig ist.
- `/zookeeper` gehört dem Server und ist als solcher markiert.
- Eine Ebene zeigt ihre ersten tausend Kinder nach Namen. Die Kindertabelle des
  Znodes darüber blättert durch alle.
- Ein Znode, den diese Verbindung nicht lesen darf, steht nur mit Namen da und
  ist als **kein Zugriff** markiert. ZooKeeper verlangt Leserecht, sogar um
  seine Größe zu nennen.

## Die Daten eines Znodes

- JSON-Daten bis 4 KB öffnen sich als Baum; sie lassen sich auch als Text öffnen.
- Andere Daten öffnen sich als Text in einem Editor. Speichern schreibt sie ganz.
- Gespeichert wird nur, wenn niemand den Znode seit dem Öffnen geändert hat und
  es noch derselbe Znode ist, nicht einer, der gelöscht und neu angelegt wurde.
  Hat er sich geändert, laden Sie ihn neu und ändern Sie ihn noch einmal.
- JSON bleibt JSON: Ein Speichern, das sich nicht parsen lässt, wird abgelehnt.
- Daten, die kein UTF-8-Text sind, werden hexadezimal gezeigt und hier nicht
  bearbeitet.

## Kinder als Zeilen

- Eine Zeile pro Kind: Name, Anfang der Daten, Größe, Version, Zahl der Kinder,
  Zeitpunkt der Änderung und Erstellung und die Sitzung eines flüchtigen.
- Die Zeilen stehen in der Reihenfolge ihrer Namen. Sie lassen sich weder
  sortieren noch filtern: ZooKeeper hat keinen Index dafür.
- Daten über 4 KB werden für die Tabelle nicht gelesen, die Zelle bleibt leer;
  öffnen Sie den Znode, um sie zu lesen.

## Das Detailfenster

Wählen Sie einen Znode im Baum und im Katalogmenü **Details**.

- Der Stat des Znodes: Versionen von Daten, Kindern und ACL, die zxids seiner
  Erstellung, letzten Änderung und letzten Änderung der Kinder, Zahl der Kinder.
- Die Sitzung, der ein flüchtiger Znode gehört.
- Eine Zeile pro Eintrag der ACL: Schema, ID und was er darf.

## Der Abschnitt Server

Ganz oben im Baum zeigt **Server**, was der Server über sich sagt: **Server**
(Version, Modus, Latenz, Verbindungen, Zahl der Znodes), **Überwachung** (jeder
Zähler), **Verbindungen** (jeder Client), **Watches** und **Konfiguration**. Die
ersten vier werden alle zehn Sekunden neu gelesen.

ZooKeeper beantwortet sie nur, wenn seine Einstellung `4lw.commands.whitelist`
sie erlaubt; seit ZooKeeper 3.5 ist ohne weitere Angabe nur `srvr` erlaubt. Ein
Bericht, den der Server nicht beantwortet, zeigt eine Zeile mit dem Wort, das
hinzuzufügen ist, etwa `4lw.commands.whitelist=srvr,mntr,cons,wchs,conf`.

Dieselben Zähler lassen sich auf einem Dashboard zeichnen: Die Vorlage
**ZooKeeper-Server** zeigt Pakete, Znodes, Latenz, Verbindungen, offene Anfragen
und Watches. Sie braucht ein erlaubtes `mntr`.

## Znodes finden

Tippen Sie in das Feld über dem Baum und drücken Sie die Suchschaltfläche, um die
Namen aller Znodes unterhalb der Spitze oder des gewählten Znodes zu durchsuchen.
ZooKeeper hat keinen Namensindex, also geht die Suche den Baum durch; sie hält
nach fünfzigtausend Znodes oder bei Zeitablauf an und sagt das. Ebenen, die diese
Verbindung nicht auflisten darf, werden übersprungen, und die Antwort sagt, dass
die Suche unvollständig sein kann. Gefundene Znodes erscheinen an ihrer Stelle im
Baum.

## Herunterladen

Die Kindertabelle eines Znodes lässt sich ganz herunterladen, in der Reihenfolge
der Namen. Auch ein Bericht lässt sich herunterladen.

## Znodes anlegen und löschen

Wählen Sie einen Znode im Baum und öffnen Sie das Katalogmenü.

- **Neuer Znode ganz oben** legt einen an der Spitze des Baums oder des
  Wurzelpfads an. **Neuer Znode darin** legt einen unter dem gewählten an. Geben
  Sie einen Namen und auf Wunsch Daten als Text an. **Sequenziell** lässt
  ZooKeeper eine zehnstellige Nummer an den Namen hängen; der neue Znode öffnet
  sich. Flüchtige Znodes werden nicht angeboten: Einer verschwände sofort.
- **Löschen** entfernt die gewählten Znodes. Einer mit Kindern wird nicht
  gelöscht.
- **Mit Kindern löschen** sagt zuerst, wie viele Znodes gehen, und nennt die
  ersten. Mehr als zehntausend werden von hier nicht gelöscht; nutzen Sie
  `deleteall` in zkCli. `/zookeeper` gehört dem Server und wird nicht gelöscht.
- **ACL ändern** öffnet sich mit der ACL des Znodes, ein Eintrag pro Zeile, wie
  zkCli ihn schreibt: `Schema:ID:Rechte`, die Rechte Buchstaben aus `cdrwa` —
  anlegen, löschen, lesen, schreiben, verwalten. `world:anyone:r` etwa lässt
  jeden lesen und sonst nichts. **Auch jeder Znode darunter** wendet sie auf den
  ganzen Teilbaum an. Vorher werden Sie gewarnt, wenn diese Verbindung die ACL
  danach nicht mehr ändern dürfte.

## zkCli

**Terminal** bei einer ZooKeeper-Verbindung öffnet `zkCli`, den Client, der mit
ZooKeeper kommt, verbunden mit Server und Wurzelpfad der Verbindung. Er läuft in
einem Container, den der Server startet; der Server muss also Container starten
dürfen, und es geht nicht durch einen SSH-Tunnel.

zkCli lässt sich beim Start kein Digest-Passwort mitgeben: Er nimmt es nur als
eingetippten Befehl an. Bei einer Verbindung mit **Digest**-Benutzer öffnet sich
das Terminal verbunden, aber nicht angemeldet, und die erste Zeile sagt das.
Tippen Sie `addauth digest benutzer:passwort`, um Znodes zu lesen und zu ändern,
deren ACL diesen Benutzer verlangt. Das Passwort wird nicht für Sie eingesetzt
und von DataPlayer nie gezeigt.

## Ein eigener ZooKeeper

**Dienste** kann einen ZooKeeper auf dieser Maschine starten, wenn dieser Server
Container starten darf. Er fragt nach keinem Passwort — ZooKeeper hat keines für
den ganzen Server; wer was darf, sagt die ACL jedes Znodes — und ist nur von
dieser Maschine aus erreichbar. Er beantwortet die Berichte oben, und seine
Verbindung wird für Sie angelegt.

Er kommt mit einem Übungsbaum unter `/lab`: Konfiguration als JSON, ein Register
von Dienstinstanzen, eine Wahl und eine Warteschlange aus sequenziellen Znodes,
als Bytes gespeicherte Zähler, eine Sperre und `/lab/private`, das nur der
Digest-Benutzer `lab` mit dem Passwort `lab` lesen darf. Eine Digest-Verbindung
als dieser Benutzer zeigt den Unterschied.

## Was ZooKeeper hier noch nicht hat

- Einen Znode auf Änderungen beobachten: Aktualisieren Sie von Hand
- Znodes in eine andere Verbindung kopieren und Sicherungen. ZooKeeper bietet
  beides nicht über seine Clients: Seine Sicherungen sind die Snapshot-Dateien
  auf dem Server selbst.
