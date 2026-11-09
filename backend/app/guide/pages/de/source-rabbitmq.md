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
- Berichte des Brokers: Überblick, Knoten, Alarme, Verbindungen
- Nachrichten pro Sekunde und Wartendes je Queue auf einem Dashboard
- Queues, Streams und Exchanges nach Namen finden
- rabbitmqadmin, für die Verbindung eingerichtet, in einem Terminal

## Was Sie ändern können

- Nachrichten an einen Stream, einzeln oder als Zeilen eingefügt
- Eine Nachricht an einen Exchange oder eine Queue veröffentlicht
- Neue Queues, Streams und Exchanges, und ihr Löschen
- Bindungen angelegt und entfernt
- Eine Queue geleert, oder einmal in ihre Nachrichten geschaut
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
- **Adresse für den Browser**: wohin **Management öffnen** im Menü des Katalogs
  führt, wenn Ihr Browser die Management-Seite unter einer anderen Adresse
  erreicht als DataPlayer; leer für die Management-Adresse;
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

## Nachrichten an einen Stream senden

- **+** über den Zeilen eines Streams fügt eine Nachricht hinzu. Füllen Sie,
  was Sie brauchen: alles darf leer bleiben. Sie geht über den
  Standard-Exchange, mit dem Namen des Streams als Routing-Key.
- **body** ist Text; `0x` gefolgt von Hex-Ziffern wird als diese Bytes
  gesendet. Lassen Sie ihn leer und füllen Sie die `body.`-Felder, um ein
  JSON-Objekt daraus zu senden.
- **headers** ist ein JSON-Objekt, etwa `{"source": "manual"}`;
  **properties** ist ein JSON-Objekt aus dem, was AMQP benennt: `message_id`,
  `correlation_id`, `reply_to`, `priority`, `expiration`, `type`, `app_id`,
  `delivery_mode`.
- Ein leerer **timestamp** sendet keinen.
- In einen Stream eingefügte Zeilen werden als Nachrichten gesendet. Lässt sich
  ein Wert nicht lesen, wird nichts gesendet und die Zelle genannt.
- Die neue Zeile zeigt keinen Offset, bis die Seite neu gelesen wird: den
  vergibt der Stream.

## Queues, Streams und Exchanges ändern

Haken Sie eine Queue, einen Stream oder einen Exchange an, oder nichts auf
seiner Ebene, und öffnen Sie das Menü des Katalogs:

- **Neue Queue**, **Neuer Stream**, **Neuer Exchange** — jeweils auf ihrer
  Ebene. Eine Queue ist classic oder quorum; ein Stream behält Nachrichten für
  eine Dauer wie `7D` und bis zu einer Größe; Argumente sind ein `Name=Wert` pro
  Zeile, etwa `x-max-length=10000`.
- **Veröffentlichen** — eine Nachricht an einen Exchange mit Routing-Key oder
  an eine Queue. Eine Nachricht, die der Exchange an keine Queue leitet, geht
  verloren, und das Fenster sagt es.
- **Binden** — von einem Exchange an die angehakte Queue, oder vom angehakten
  Exchange an eine Queue oder einen Exchange, mit Routing-Key. **Lösen** wählt
  eine der Bindungen des angehakten Knotens.
- **Leeren** — alle bereiten Nachrichten einer Queue gehen; abgeholte und
  noch nicht bestätigte bleiben bei ihren Consumern.
- **Löschen** — das Fenster sagt, wie viele Nachrichten und Bindungen gehen.
  RabbitMQs eigene Exchanges werden nicht gelöscht.

## Hineinschauen

Die Nachrichten einer Queue werden beim Öffnen nicht gezeigt: sie zu lesen
hieße, sie zu nehmen. **Hineinschauen** nimmt bis zu hundert, legt sie sofort
zurück und öffnet das Gelesene in einem Tab.

- Jede Nachricht kommt als **erneut zugestellt** markiert zurück. Eine
  Quorum-Queue zählt den Blick auf ihr Zustelllimit an, nach dem eine Nachricht
  in den Dead-Letter geht oder verworfen wird, und ein Consumer kann die
  Nachrichten in anderer Reihenfolge bekommen. Das Fenster fragt vorher.
- Der Tab ist der Blick, wie er genommen wurde. Durchblättern liest die Queue
  nicht erneut; für einen neuen Blick schauen Sie noch einmal hinein.
- Ein Blick bleibt, solange DataPlayer läuft, und eine Weile nach dem letzten
  Öffnen.

## Der Abschnitt Broker

Oben im Katalog sammelt **Broker**, was der Broker über sich sagt:

- **Überblick** — die Version, wie viele Verbindungen, Kanäle, Queues,
  Exchanges und Consumer, bereite und unbestätigte Nachrichten, und Nachrichten
  pro Sekunde ein und aus;
- **Knoten** — Speicher jedes Knotens und seine Grenze, freie Platte und ihre
  Schwelle, Dateideskriptoren und Laufzeit;
- **Alarme** — ein Knoten mit zu wenig Speicher oder Platte. Solange ein Alarm
  besteht, blockiert RabbitMQ alle Absender; ist alles in Ordnung, ist der
  Bericht leer;
- **Verbindungen** und **Kanäle** — jeder Client, sein Benutzer und virtueller
  Host, seine Kanäle, Consumer, Prefetch und abgeholte, unbestätigte
  Nachrichten;
- **Richtlinien** — jede Richtlinie, worauf sie passt und was sie setzt.

Überblick, Alarme und Verbindungen aktualisieren sich alle zehn Sekunden. Eine
lange Liste zeigt die ersten fünfhundert und sagt es.

## Dashboards und Suche

- Das Dashboard **RabbitMQ-Broker** zeichnet Nachrichten pro Sekunde, was in
  jeder Queue wartet und was abgeholt und unbestätigt ist, Verbindungen und
  Alarme, für die ersten hundert Queues nach Namen.
- Die Suche in der Kopfzeile findet Queues, Streams und Exchanges nach Namen,
  in jedem virtuellen Host, den die Verbindung sieht.

## In einer Pipeline

RabbitMQ kann in der Mitte einer Pipeline stehen, wie ein Kafka-Topic: eine
Verknüpfung schickt Zeilen hinein, andere tragen das Angekommene in Tabellen.

- **Zeilen hinzufügen** an einen Exchange, eine Queue oder einen Stream schickt
  jede Zeile als Nachricht. Jede Spalte, die nicht zur Nachricht selbst gehört,
  wird ein Feld eines JSON-Inhalts unter ihrem Namen: eine Tabellenzeile oder ein
  Binance-Trade kommt als `{"price": …, "qty": …}` an, gleichnamige Spalten
  paaren sich von selbst. An einen Exchange paaren Sie eine Spalte mit
  **routing_key**: eine Zeile ohne geht dorthin, wohin der Exchange einen leeren
  Schlüssel schickt.
- **Neue Nachrichten zu einer Tabelle hinzufügen** liest aus einem Stream nur, was
  seit dem letzten Lauf der Verknüpfung ankam. Die Stelle hält DataPlayer, nach
  Offset. **Neue Nachrichten zu einer neuen Tabelle hinzufügen** gibt der
  angelegten Tabelle einen Schlüssel auf den Offset, so bleibt eine zweimal
  geschriebene Nachricht einmal.
- Dieselben Verknüpfungen aus einer Queue holen ihre wartenden Nachrichten wie
  jeder Consumer: jeder Block wird erst bestätigt, wenn er geschrieben ist.
  Scheitert ein Lauf dazwischen, geht der Block in die Queue zurück und wird
  erneut geholt, als erneut zugestellt markiert. Andere Consumer teilen sich die
  Nachrichten mit der Verknüpfung; für alle geben Sie ihr eine eigene Queue, an
  den Exchange gebunden.
- Die Spalten einer Queue sind die der Nachricht — der Inhalt kommt ganz — und
  **Erster Lauf liest** bedeutet für sie nichts: sie holt immer, was wartet.
- **Folgen** trägt Angekommenes binnen Sekunden, aus einem Stream oder einer
  Queue, wie aus einem Topic.

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

## Ein eigenes RabbitMQ

**Dienste** kann einen RabbitMQ-Broker auf diesem Rechner starten, wenn dieser
Server Container starten darf. Sein Benutzer ist `dataplayer`, sein Passwort
wird für Sie erfunden, wenn Sie keines angeben; seine Verbindung wird für Sie
angelegt.

Fordern Sie Beispieldaten an, um ein Lab zu bekommen:

- `lab.orders` — ein Topic-Exchange, der `orders.new` und `orders.paid` leitet;
- `lab.billing` — eine Classic-Queue, an `orders.#` gebunden, sechzig wartende
  Bestellungen, Abgelehntes geht an `lab.dead-letter`;
- `lab.shipping` — eine Quorum-Queue, an `orders.paid` gebunden, sie hält also
  nur die bezahlten Bestellungen;
- `lab.dead-letter` und `lab.dead` — ein Fanout-Exchange und die Queue dahinter;
- `lab.alerts` und `lab.alerts.critical` — ein Headers-Exchange und eine Queue,
  die nur die Alarme mit `level` gleich `critical` nimmt;
- `lab.trades` — ein Stream aus dreihundert JSON-Trades über einen Tag und
  einigen Sensorwerten als Bytes, hexadezimal angezeigt.

Im Lab holt niemand etwas ab, also bleibt jede Zahl, wo sie war.

Die Zeile des Dienstes zeigt seinen AMQP-Port und den Port seiner
Management-API, mit einem Link zur Management-Seite. **Management öffnen** im Menü
der Verbindung öffnet dieselbe Seite. DataPlayer selbst erreicht den Broker über
den Namen des Containers, so dass beides von diesem Rechner aus funktioniert.
