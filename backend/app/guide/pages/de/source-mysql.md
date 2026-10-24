# MySQL

Ein MySQL- oder MariaDB-Server. Sie durchsuchen seine Datenbanken, lesen
Tabellen und Ansichten Seite für Seite, sehen, wie eine Tabelle aufgebaut ist,
lesen ihre DDL, wie der Server sie schreibt, und führen SQL in einer Konsole aus.
Wie Verbindungen im Allgemeinen funktionieren, steht auf der Seite
[Verbindungen](connections.md).

## Was Sie sehen können

- Datenbanken, Tabellen und Ansichten, ihre Zeilen sortiert und gefiltert
- Spalten, Schlüssel, Prüfungen und Indizes einer Tabelle, und ihre Zieltabellen
- Wohin der Fremdschlüssel einer Zeile führt und was auf sie zeigt
- Die DDL einer Relation, wie der Server sie schreibt
- Wie groß eine Tabelle ist und wann sie erstellt und zuletzt beschrieben wurde
- Die Ergebnisse Ihres SQL und den Plan des Servers für eine Abfrage
- Jede passende Zeile, heruntergeladen als Datei
- Prozesse, Variablen, Status, Benutzer, Routinen, Trigger, Ereignisse, Engines

## Was Sie ändern können

- Tabellendaten: Zellen bearbeiten, Blöcke einfügen, Zeilen einfügen und löschen
- Spalten, Indizes, eindeutige Schlüssel und Fremdschlüssel
- Neue Tabellen, Objekt für Objekt entworfen oder aus Zeilen gemacht
- Daten und Struktur über SQL in der Konsole
- Was andere Verbindungen ausführen: Anweisung anhalten, Verbindung schließen
- Datenbanken: erstellen und löschen
- Tabellen und Ansichten: umbenennen, in andere Datenbank verschieben, löschen
- Tabellen mit Struktur, in eine andere MySQL- oder MariaDB-Verbindung kopiert
- Sicherungen der Datenbank der Verbindung, und ihre Wiederherstellung

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach:

- **Host** und **Port**, 3306, wenn der Server nichts anderes sagt;
- **Authentifizierung**: ein Benutzer und ein Passwort oder ein Benutzer ohne
  Passwort;
- **Datenbank**: wo sich der Katalog öffnet. Sie kann leer bleiben. Jede
  Datenbank, die der Benutzer sehen darf, steht in jedem Fall im Katalog.

Eine Verbindungszeichenfolge wie `mysql://ann@db.example.com:3306/sales`, in
**URL** eingefügt, füllt diese Felder; `mariadb://` wird genauso gelesen. Ein
Passwort in der eingefügten Zeichenfolge wandert in das Passwortfeld und
verlässt die Zeichenfolge.

Die Verbindung ist verschlüsselt, wenn der Server TLS anbietet, und bleibt
unverschlüsselt, wenn nicht. Das Zertifikat des Servers wird nicht geprüft.

Unterstützt werden MySQL ab 8.0.16 und MariaDB ab 10.6. Ein älterer Server wird
beim Prüfen der Verbindung abgelehnt, mit Nennung seiner Version.

## Der Katalog

- Die erste Ebene sind Datenbanken. Die, die die Verbindung nennt, steht zuerst;
  `mysql`, `information_schema`, `performance_schema` und `sys` gehören dem
  Server und sind entsprechend markiert.
- In einer Datenbank stehen ihre Tabellen und Ansichten. Das Drücken einer
  öffnet ihre Zeilen in einem Tab.
- Eine Tabelle sagt ungefähr, wie viele Zeilen sie enthält. Die Zahl ist die
  Schätzung des Servers, die MySQL bis zu einen Tag behalten kann; niemand zählt
  die Zeilen.
- **Details** sagen, wie viele Spalten, Indizes und Einschränkungen eine
  Relation hat, wie groß sie ist und wann sie erstellt und zuletzt beschrieben
  wurde.
- **DDL anzeigen** zeigt die Anweisung `CREATE TABLE` oder `CREATE VIEW`, die
  der Server selbst ausgibt.
- **System**, nach den Datenbanken, ist ein Abschnitt von Berichten, die der
  Server über sich selbst gibt (siehe **Berichte** unten).
- Die Suche in der Kopfzeile findet Datenbanken und Tabellen nach Namen und
  Tabellen nach ihren Spalten und den Kommentaren zu ihnen und ihren Spalten.

## Zeilen lesen

Eine Tabelle öffnet sich als Datentabelle, Seite für Seite, vom Server sortiert
und gefiltert wie eine PostgreSQL-Tabelle. Was eine Spalte anbietet, hängt von
ihrem Typ ab: Vergleiche für Zahlen, Daten und Text; „enthält“ und „beginnt
mit“ für Text; Gleichheit und „einer aus einer Liste“ für Enums; „leer“ oder
„nicht leer“ für jede Spalte.

- Seiten folgen dem Primärschlüssel. Eine Tabelle ohne ihn folgt einem
  eindeutigen Schlüssel über Spalten, die nicht leer sein können, der Reihenfolge,
  in der InnoDB eine solche Tabelle hält. Eine Tabelle mit keinem von beiden und
  eine Ansicht stehen in der Reihenfolge, die der Server liefert.
- Ein `%` oder `_` in einem Textfilter wird als es selbst gesucht.
- **Herunterladen** fragt nach **Aktuelle Seite** oder **Alle passenden Zeilen**.
  Jede Zeile wird vom Server gelesen, während sie in die Datei geschrieben wird,
  in der Reihenfolge der Seite und mit ihren Filtern.

Wie Werte gezeigt werden:

- `DECIMAL` und große vorzeichenlose Ganzzahlen genau wie gespeichert;
- `BIT` als Zahl;
- `TIMESTAMP` in UTC, mit `+00:00`. `DATETIME` so, wie es geschrieben wurde,
  ohne Zeitzone, weil es keine hat;
- `TIME` so, wie MySQL es schreibt, was negativ oder mehr als 24 Stunden sein
  kann;
- ein Nulldatum wie `0000-00-00` so, wie der Server es schreibt;
- Geometrie als Text, etwa `POINT(1 2)`;
- binäre Spalten hexadezimal, etwa `0x00FF`.

## Zeilen bearbeiten

Mit Zugriff auf **Zeilen bearbeiten** wird eine Tabelle in ihrer Datentabelle
bearbeitet wie eine PostgreSQL-Tabelle: auf eine Zelle doppelklicken, einen
Block einfügen, **Zeile einfügen**, Zeilen anhaken und **Ausgewählte Zeilen
löschen**.

- Eine Zeile wird über ihren Primärschlüssel wiedergefunden oder über einen
  eindeutigen Schlüssel über Spalten, die nicht leer sein können. Eine Zeile
  einer Tabelle mit keinem von beiden wird über alle ihre Werte gefunden, und es
  wird jeweils eine Zeile geändert: Zeilen, die in jedem Wert gleich sind, sind
  austauschbar. Zwei Zeilen, die sich nur in einer Gleitkomma-, JSON- oder
  Geometriespalte unterscheiden, lassen sich nicht auseinanderhalten, und eine
  Änderung an einer wird mit diesem Grund abgelehnt.
- Wenn jemand eine Zeile in irgendeiner Spalte geändert hat, nachdem Sie sie
  gelesen haben, wird Ihre Änderung abgelehnt, statt über seine geschrieben.
  Laden Sie neu und versuchen Sie es erneut.
- Ein Wert, den die Spalte nicht aufnehmen kann, wird abgelehnt, bevor etwas
  geschrieben wird, und die Zellen mit solchen Werten werden genannt. Von einem
  eingefügten Block landet nichts, bis alles landen kann.
- Schreiben Sie Werte so, wie die Datentabelle sie zeigt: binär als `0x…`,
  Geometrie als WKT wie `POINT(1 2)`, einen `TIMESTAMP` mit seinem Versatz.
- Eine Zelle in einem Fremdschlüssel hat einen Pfeil, der die Zeile öffnet, auf
  die er zeigt, und **Was auf diese Zeile verweist** öffnet die Zeilen, die
  hierher zeigen, in dieser oder einer anderen Datenbank des Servers.

## Die Struktur ändern

**Struktur** einer Tabelle ändert sie wie eine PostgreSQL-Tabelle: eine Spalte
hinzufügen, umbenennen und löschen, ihren Standardwert setzen oder entfernen,
einen Wert verlangen oder nicht mehr verlangen, ihren Typ ändern, Indizes,
eindeutige Schlüssel und Fremdschlüssel hinzufügen und löschen.

- Alles andere an einer Spalte – ihr Standardwert, Kommentar, Zeichensatz,
  AUTO_INCREMENT – bleibt erhalten, wenn sich ihr Typ oder ihre
  NULL-Fähigkeit ändert.
- Eine Änderung, der die Zeilen bereits widersprechen, wird nicht gemacht, und
  die Anzahl wird gezeigt: Zeilen ohne Wert, Werte, die sich wiederholen, Zeilen,
  die ins Leere zeigen, Werte, die der neue Typ nicht aufnehmen kann. Letztere
  kann MySQL erst zählen, nachdem es die Änderung versucht hat und abgelehnt
  wurde; geändert wird in keinem Fall etwas.
- Die angebotenen Typen sind die von MySQL: Text, langer Text, Ganzzahl, große
  Ganzzahl, Dezimalzahl, Gleitkommazahl, Boolesch als 0 oder 1, Datum, Datum und
  Uhrzeit, Zeitstempel, JSON und eine UUID als Text.
- Indizes sind B-Baum, Volltext (nur Textspalten) oder räumlich (eine
  Geometriespalte, die einen Wert verlangt). MySQL benennt einen neuen Index oder
  Schlüssel selbst.
- Ein eindeutiger Schlüssel und sein Index sind in MySQL eins; löschen Sie ihn
  als Schlüssel.
- `SET DEFAULT` wird für einen Fremdschlüssel nicht angeboten: InnoDB führt es
  nicht aus.

## Eine Tabelle erstellen

**Tabelle erstellen** im Aktionsmenü einer Datenbank öffnet den Tabellenentwurf
wie bei PostgreSQL. Der Plan ist ein einziges `CREATE TABLE` mit jedem
Schlüssel, jeder Prüfung, jedem Fremdschlüssel und jedem Index darin, sodass
die Tabelle ganz oder gar nicht entsteht.

- Was MySQL nicht hat, wird an dem Objekt markiert, das danach fragt, bevor Sie
  den Plan prüfen können: ein aufschiebbarer Schlüssel, zusätzliche Spalten in
  einem Index, ein Index über einen Teil der Zeilen, NULL-Werte zuerst oder
  zuletzt sortiert, eine nicht protokollierte oder partitionierte Tabelle.
- Eine Identitätsspalte ist AUTO_INCREMENT: eine pro Tabelle, am Anfang eines
  Schlüssels, mit einem Startwert, aber ohne eigene Schrittweite.
- Ein Primärschlüssel heißt immer PRIMARY.
- Zeilen, die als Tabelle behalten werden, oder eine in eine Tabelle geladene
  Datei werden vor dem Erstellen der Tabelle gegen die gewählten Typen geprüft;
  werden sie trotzdem abgelehnt, wird die neue Tabelle wieder entfernt.

## SQL-Konsole

**Neue Abfrage** unter **Abfragen** auf der linken Leiste startet eine auf der
Verbindung, und **Als Abfrage öffnen** über einer Tabelle startet eine auf
dieser Tabelle. Sie funktioniert wie die PostgreSQL-Konsole – Lesen, sofort
festgeschriebene oder in einer **Manuell**-Transaktion gehaltene Änderungen,
**Erklären**, Vervollständigung und Formatierung – mit diesen Unterschieden:

- Die über dem Editor gewählte Datenbank ist die Standarddatenbank, wie `USE`
  sie setzen würde; eine Datenbank auf einmal.
- Parameter werden `:name` geschrieben. Jeder Wert wird als Text gesendet, daher
  kann eine Zahl, die der Server als Zahl braucht, etwa nach `LIMIT`, kein
  Parameter sein.
- Eine Strukturänderung – `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `RENAME` –
  läuft für sich. MySQL schreibt sie sofort fest, zusammen mit allem davor, daher
  kann sie keine Ausführung mit anderen Anweisungen teilen, nicht in einer von
  Ihnen gehaltenen Transaktion laufen und nicht vorher ausprobiert werden. Die
  Konsole fragt, bevor sie eine ausführt, und sagt das.
- Eine Anweisung, die in einer von Ihnen gehaltenen Transaktion scheitert, lässt
  die Transaktion offen; ein Deadlock beendet sie.
- **Stoppen** und das Zeitlimit beenden eine Anweisung mit `KILL QUERY`.
- Benutzer, Rechte, Routinen, Trigger und Ereignisse werden nicht in der Konsole
  geändert. `LOAD DATA`, `SELECT … INTO OUTFILE` und `CALL` werden nicht
  ausgeführt.

## Berichte

**System** im Katalog enthält acht Berichte über den Server. Sie werden wie
Tabellen gelesen und können sortiert, gefiltert, heruntergeladen und
diagrammiert werden. **Anweisung anzeigen** zeigt das SQL, das ein Bericht
ausführt.

- **Prozesse**: die jetzt offenen Verbindungen und was jede ausführt. Jede Zeile
  hat **Abfrage abbrechen**, das die Anweisung anhält und die Verbindung
  behält, und **Beenden**, das die Verbindung schließt. Der Bericht liest sich
  alle fünf Sekunden selbst neu.
- **Variablen**: jede globale Einstellung des Servers.
- **Status**: die Zähler, die der Server seit seinem Start führt. Er liest sich
  alle zehn Sekunden selbst neu.
- **Benutzer**: die Konten, die sich verbinden dürfen, und von welchen Hosts.
  **Neuer Benutzer** über den Zeilen legt eines an: einen Namen, den Host, von
  dem es sich verbinden darf (`%` für überall), und ein Passwort. Es erhält
  nichts oder, wenn angehakt, das Lesen der Datenbank der Verbindung. Nur der
  Eigentümer der Verbindung hat diesen Befehl.
- **Routinen** und **Trigger** außerhalb der eigenen Datenbanken des Servers und
  die **Ereignisse**, die sein Planer ausführt.
- **Engines**: die Speicher-Engines, die der Server anbietet, und welche die
  Standard-Engine ist.

Ein Bericht zeigt nur, was der Benutzer der Verbindung sehen darf: Ein Benutzer
ohne das Recht `PROCESS` sieht nur seine eigenen Verbindungen, und **Benutzer**
wird einem verweigert, der die Datenbank `mysql` nicht lesen kann.

## Aktionen im Katalog

- **Neue Datenbank** auf der obersten Ebene des Katalogs.
- **Datenbank löschen** fragt zuerst. Eine Datenbank, die etwas enthält, wird nur
  mit angehaktem **Auch alles darin löschen** gelöscht, und was sie enthält,
  wird vor Ihrer Bestätigung gezählt.
- **Umbenennen** einer Tabelle oder Ansicht. Fremdschlüssel, die auf eine
  Tabelle zeigen, folgen ihr.
- **In Datenbank verschieben** verschiebt eine Tabelle. Eine Ansicht und eine
  Tabelle mit Triggern bleiben in ihrer Datenbank.
- **Löschen** einer oder mehrerer Relationen zusammen. Eine Tabelle, auf die
  eine Tabelle außerhalb der Auswahl verweist, wird nicht gelöscht, und die
  verweisenden Tabellen werden genannt. Bei MySQL werden auch die Ansichten
  genannt, die eine gelöschte Tabelle lesen.
- **Aus CSV laden** macht aus einer Datei eine Tabelle, jede Spalte als `TEXT`.
- **Modell als Code** schreibt eine Datenbank oder eine Auswahl für ein ORM oder
  ein Diagramm heraus.

Strukturänderungen werden nicht vorher geprobt wie bei PostgreSQL: MySQL schreibt
sie sofort fest.

## Tabellen kopieren

**Kopieren** Sie Tabellen im Katalog und **Fügen** Sie sie in eine Datenbank einer
anderen MySQL- oder MariaDB-Verbindung oder dieser **ein**. Sie kommen mit ihren
Spalten, Schlüsseln, Indizes, Prüfungen und Optionen an; das Fenster fragt
dasselbe wie bei PostgreSQL, zeigt jede Anweisung und führt nichts vor
**Kopieren** aus.

- Trigger bleiben zurück und werden im Fenster genannt. Ansichten und
  partitionierte Tabellen werden so nicht kopiert.
- Zuerst werden die Tabellen angelegt, danach kommen die Zeilen. Scheitert die
  Kopie oder wird sie angehalten, werden die von ihr angelegten Tabellen wieder
  gelöscht.
- MariaDB verwendet eine Sortierfolge, die MySQL nicht hat, daher kann eine von
  MariaDB nach MySQL kopierte Tabelle abgelehnt werden; das Fenster sagt, welcher
  Schritt sie abgelehnt hat.

Zeilen, die in eine Verbindung anderer Art eingefügt werden, gehen den Weg der
Zeilen jeder Tabelle.

## Sicherungen

**Sicherungen** im Aktionsmenü des Katalogs funktioniert wie bei PostgreSQL, für
die Datenbank, die die Verbindung nennt. Einer Verbindung ohne Datenbank wird
keine angeboten.

- Die Sicherung ist eine SQL-Datei, geschrieben von `mysqldump` oder bei MariaDB
  von `mariadb-dump`, in der Version des Servers selbst, mit Routinen, Triggern
  und Ereignissen.
- **Wiederherstellen** löscht jede Tabelle, Ansicht und Routine, die die
  Sicherung enthält, und legt sie neu an. Eine Sicherung aus MariaDB wird nur in
  MariaDB wiederhergestellt, eine aus MySQL nur in MySQL.

## Dashboards

Eine MySQL-Verbindung kann an Dashboards melden. Das Layout heißt
**MySQL-Server**: Verbindungen, Anweisungen, Zeilen, Lesevorgänge im Pufferpool,
Netzwerkverkehr, langsame Abfragen und abgebrochene Verbindungen sowie die Größe
der Datenbank der Verbindung. Die Zähler gelten für den ganzen Server: MySQL
führt sie nicht pro Datenbank.

## Ein eigener Server

**Neue Verbindung** bietet **MySQL hier starten** und **MariaDB hier starten**:
einen auf diesem Rechner gestarteten Server, gespeichert als Verbindung, die
sich als sein root anmeldet. Mit Beispieldaten öffnet er sich auf `demo_lab` –
Organisationen, Personen, Projekte, einige hundert Aufgaben und Messungen – mit
etwas für jeden Bildschirm: generierte Spalten, JSON, eine partitionierte
Tabelle, Volltext- und räumliche Schlüssel, eine Ansicht, ein Trigger und eine
Tabelle ohne Schlüssel.

## Was MySQL hier noch nicht hat

- Eine Datenbank kann nicht umbenannt werden; MySQL hat dafür keinen Weg.
