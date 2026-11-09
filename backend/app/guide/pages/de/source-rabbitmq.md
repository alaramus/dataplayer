# RabbitMQ

Ein RabbitMQ-Broker. Sie sehen seine virtuellen Hosts, Queues, Streams und
Exchanges, wie viele Nachrichten warten und wer sie abholt, und lesen die
Nachrichten eines Streams als Zeilen. Wie Verbindungen allgemein funktionieren,
steht auf der Seite [Verbindungen](connections.md).

## Was Sie sehen können

- Virtuelle Hosts und in jedem seine Queues, Streams und Exchanges
- Wie viele Nachrichten in einer Queue warten und wie viele unbestätigt sind
- Wer aus einer Queue liest, und Nachrichten pro Sekunde ein und aus
- Was woran gebunden ist: Exchanges einer Queue, Queues eines Exchange
- Nachrichten eines Streams als Zeilen, neueste zuerst, ab Offset oder Zeit
- Die Felder von JSON-Nachrichten, jedes in einer eigenen Spalte
- Nachrichten eines Streams oder die Bindungen als Datei herunterladen
- rabbitmqadmin, für die Verbindung eingerichtet, in einem Terminal

## Was Sie ändern können

- Alles, was rabbitmqadmin ändern kann, im Terminal eingegeben

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach:

- **Host** und **AMQP-Port**: wo der Broker AMQP annimmt, standardmäßig 5672,
  mit TLS 5671;
- **Management-Adresse**: wo seine Management-API antwortet. Leer bedeutet
  `http://`, der Host und Port 15672, oder `https://` mit TLS. RabbitMQ
  antwortet dort nur mit eingeschaltetem Management-Plugin; die offiziellen
  `-management`-Images haben es;
- **Benutzer** und **Passwort**: ein RabbitMQ-Benutzer für beides;
- **Virtueller Host**: leer für alle virtuellen Hosts, die der Benutzer sehen
  darf, oder ein Name wie `/`;
- **TLS** und **CA-Zertifikat**: eine verschlüsselte Verbindung und die
  Stelle, die das Zertifikat des Brokers signiert hat, wenn das System ihr
  nicht vertraut.

Eine Verbindungszeichenfolge `amqp://user:password@host:5672/vhost` füllt das
Formular; `amqps://` ist TLS, und `%2F` im Pfad ist der virtuelle Host `/`.

Die Prüfung fragt zuerst die Management-API, dann AMQP. Lehnt nur AMQP ab —
ein virtueller Host, den der Benutzer nicht öffnen darf, ein unerreichbarer
Port —, wird die Verbindung trotzdem gespeichert und sagt, warum: der Katalog
funktioniert, die Nachrichten eines Streams nicht. Ein SSH-Tunnel wird nicht
unterstützt.

## Der Katalog

- Bei mehreren virtuellen Hosts listet die oberste Ebene sie auf; bei einem,
  oder einem in der Verbindung genannten, sind es seine **Queues**,
  **Streams** und **Exchanges**.
- Eine Queue zeigt ihren Typ (classic oder quorum), wie viele Nachrichten
  warten, wie viele abgeholt und noch nicht bestätigt sind und wie viele
  Consumer sie hat.
- Ein Stream zeigt, wie viele Nachrichten er hält und wer ihn liest.
- Ein Exchange zeigt seinen Typ: direct, topic, fanout oder headers. Ihre
  Exchanges kommen zuerst, dann die, die RabbitMQ in jedem virtuellen Host
  anlegt; der Standard-Exchange, der keinen Namen hat, heißt **(Standard)**.
- Die Zahlen sind RabbitMQs eigene Messungen alle paar Sekunden, eine Zahl
  kann also kurz hinterherhinken.
- Eine Ebene zeigt die ersten fünfhundert nach Namen.

## Eine Queue und ein Exchange

Eine Queue behält eine Nachricht, bis ein Consumer sie abholt, und vergisst sie
dann; ihre Nachrichten werden daher nicht angezeigt: sie zu lesen hieße, sie
wegzunehmen.

- Eine Queue öffnet sich mit ihren Bindungen: der Exchange, der zu ihr leitet,
  der Routing-Key und die Argumente. Jede Queue ist mit ihrem eigenen Namen an
  den Standard-Exchange gebunden.
- Ein Exchange öffnet sich mit seinen Zielen: Queue oder Exchange, Routing-Key
  und Argumente.

## Die Nachrichten eines Streams

Ein Stream behält seine Nachrichten für seine Aufbewahrungsdauer, wie ein Log,
und jeder kann ihn von jeder Stelle lesen, ohne etwas wegzunehmen.

- Eine Zeile pro Nachricht: Offset, Zeit, Exchange und Routing-Key, über die
  sie kam, Content-Type, Header, weitere Eigenschaften und Inhalt.
- Sind die Inhalte JSON-Objekte, wird jedes Feld ebenfalls eine Spalte,
  benannt `body.` und das Feld. Die Felder stammen aus den zweihundert
  neuesten Nachrichten.
- Ein Inhalt, der kein Text ist, wird hexadezimal angezeigt.
- Neueste zuerst. Sortieren Sie nach **offset**, um mit den ältesten zu
  beginnen; keine andere Spalte sortiert.
- **timestamp** ist die Zeit, die der Absender auf die Nachricht gesetzt hat,
  leer, wenn er keine gesetzt hat. Ein Filter „ab“ einem Zeitpunkt beginnt das
  Lesen dort, wo der Stream selbst diesen Zeitpunkt empfangen hat, auf einen
  Nachrichtenblock genau.
- Filtern Sie nach **offset**, um zu wählen, wo das Lesen beginnt und endet.
- Filter auf den anderen Spalten durchsuchen die gelesenen Nachrichten, bis zu
  hunderttausend für eine Seite.
- Eine Seite reicht höchstens zehntausend Nachrichten vom Ende. Für weiter
  zurück filtern Sie nach Offset oder Zeit.
- Einen Stream zu lesen nimmt ihm nichts und verschiebt niemandes Stelle.

## Das Detailfenster

Wählen Sie eine Queue, einen Stream oder einen Exchange und dann **Details** im
Menü des Katalogs.

- Eine Queue: Typ, Zustand, wartende und unbestätigte Nachrichten, Nachrichten
  pro Sekunde ein und aus, Knoten und Richtlinie, jeder Consumer mit Kanal und
  Prefetch, und die Argumente, mit denen sie angelegt wurde.
- Ein Stream: Nachrichten, Segmente, Nachrichten pro Sekunde ein, wann die
  älteste behaltene Nachricht ankam, Leader und Mitglieder, Consumer und
  Argumente.
- Ein Exchange: Typ, ob er einen Neustart übersteht, ob er ungenutzt gelöscht
  wird oder intern ist, und Nachrichten pro Sekunde ein und aus.

## Herunterladen

**Herunterladen** auf einem Stream speichert die Nachrichten, die seine Seite
zeigen würde, mit ihren Filtern und ihrer Reihenfolge, bis zu zehntausend.
Eine Queue oder ein Exchange lädt die Bindungen herunter.

## rabbitmqadmin

**Terminal** auf einer RabbitMQ-Verbindung öffnet bash mit `rabbitmqadmin`,
RabbitMQs eigenem Kommandozeilen-Client der Management-API, bereits auf die
Verbindung eingestellt: Adresse, Benutzer, Passwort und virtueller Host. Tab
vervollständigt die Befehle. Probieren Sie:

- `rabbitmqadmin show overview` — der Broker auf einen Blick
- `rabbitmqadmin list queues` — alle Queues mit ihren Zählern
- `rabbitmqadmin list exchanges` — die Exchanges
- `rabbitmqadmin -V NAME list queues` — ein anderer virtueller Host

Er kann Queues und Exchanges anlegen, löschen und leeren, Nachrichten
veröffentlichen und abholen und Definitionen exportieren; was er ändert, ändert
sich sofort auf dem Broker. Das Terminal läuft in einem Container auf dem
DataPlayer-Server; dieser muss Container starten dürfen, und die
Management-Adresse muss von dort erreichbar sein.
