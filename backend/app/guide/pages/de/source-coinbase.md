# Coinbase Exchange

Die öffentlichen Marktdaten von Coinbase Exchange: seine Spot-Produkte. Sie
sehen den letzten Tag und die Regeln jedes Produkts, lesen seine Kerzen, jeden
Trade seit Beginn und sein Orderbuch als Zeilen und beobachten seinen Markt
live. Auf Coinbase wird nichts geändert, und kein Schlüssel ist nötig. Wie
Verbindungen allgemein funktionieren, steht auf der Seite
[Verbindungen](connections.md).

## Was Sie sehen können

- Spot-Produkte nach Kurswährung
- Die letzten 24 Stunden jedes Produkts: Preis, Änderung, Hoch, Tief, Volumen
- Die Handelsregeln jedes Produkts: Preisschritt, Mengenschritt, Mindestorder
- Die Kerzen eines Produkts: 1 und 5 Minuten, 15 Minuten, 1 und 6 Stunden, Tag
- Jeden Trade eines Produkts seit seiner Listung, nach Nummer
- Das Orderbuch eines Produkts, Gebote und Angebote mit laufender Summe
- Den Markt eines Produkts live: Chart, Orderbuch und Trades auf einem Schirm
- Jedes davon als Datei heruntergeladen
- Die Uhr von Coinbase und wie viel des Anfragelimits verbraucht ist
- Das Anfragelimit und die Antworten von Coinbase auf einem Dashboard
- Produkte, nach Name oder Asset gefunden
- Trades oder Kerzen eines Produkts in einer Pipeline, je Lauf nur das Neue

## Was Sie ändern können

- Nichts: Marktdaten werden nur gelesen

## Was Coinbase Exchange hier noch nicht hat

- Ihr Konto: ein Schlüssel wird noch nicht abgefragt

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach dem **Endpunkt**:

- **Coinbase Exchange** — `api.exchange.coinbase.com` und sein Feed auf
  `ws-feed.exchange.coinbase.com`;
- **Sandbox** — die öffentliche Sandbox von Coinbase mit eigenen Preisen.

## Der Katalog

- **Börse** zuerst: was Coinbase und diese Verbindung über sich sagen.
- **Märkte**: ein Ordner mit allen Produkten. Eine Zeile öffnet sofort ihren
  Chart **Markt**.
- **Spot** enthält **Ticker**, **Symbole** und einen Ordner je Kurswährung,
  die mit den meisten Produkten zuerst.
- Eine Kurswährung enthält ihre Produkte, nur die gerade gehandelten, etwa
  `BTC-USD`.
- Ein Produkt enthält **Markt**, **Kerzen** mit einer Reihe je Intervall,
  **Trades** und **Orderbuch**.

## Markt

**Markt**, der erste Knoten jedes Produkts, öffnet einen Tab, der sich mit
dem Markt bewegt: der Tag oben, Kerzen über ihrem Volumen, das Orderbuch mit
der Tiefe jeder Stufe und die Trades, wie sie geschehen.

- Das Kerzenintervall wählen Sie oben; scrollen oder ziehen Sie den Chart,
  um zurückzublicken.
- Nach dem ersten Moment kommt alles aus dem Feed von Coinbase, der nichts
  vom Anfragelimit kostet. Kerzen sendet Coinbase darin nicht, darum zeichnet
  DataPlayer die noch offene Kerze aus den eintreffenden Trades.
- Fällt das Netz aus, sagt der Tab es und kommt von selbst zurück.

## Tabellen

- **Ticker**: eine Zeile je Produkt, die mit dem meisten Volumen zuerst. Jede
  Spalte sortiert und filtert. Wird alle zehn Sekunden aufgefrischt. Coinbase
  gibt das Tagesvolumen nur im Basis-Asset, darum gibt es kein
  **quote_volume**.
- **Symbole**: eine Zeile je Produkt mit seinen Regeln.
- **Kerzen**: die neuesten zuerst; nach **open_time** sortiert beginnt es mit
  den ältesten, ein Filter darauf wählt, wo das Lesen beginnt und endet. Die
  noch offene Kerze sagt `closed` false. Für ein Intervall ohne Trade gibt
  Coinbase keine Kerze.
- **Trades**: die neuesten zuerst. Coinbase nummeriert die Trades eines
  Produkts der Reihe nach ab dem ersten und bewahrt alle auf: ein Filter auf
  **id** wählt, wo Sie schauen, und nach **id** sortiert beginnt es mit dem
  allerersten. Einen Trade nach seiner Zeit finden kann Coinbase nicht, darum
  ist **time** kein Filter.
- **Orderbuch**: Gebote vom besten an, dann Angebote vom besten an. Ein Filter
  auf **level** wählt die Tiefe, bis 1.000; 100 Stufen ohne Filter. Ein Filter
  auf **side** behält eine Seite.
- **volume** ist immer im Basis-Asset. Preise und Mengen sind exakte
  Dezimalzahlen, wie Coinbase sie schreibt.

## In einer Pipeline

Die **Trades** eines Produkts und jede **Kerzen**-Reihe können eine
weiterlesende Verbindung einer Pipeline beginnen: **Neue Nachrichten an eine
Tabelle anhängen** oder **an eine neue Tabelle**, oder **Das Neueste je
Schlüssel behalten**. Jeder Lauf liest nur, was seit dem letzten kam, und
eine eingeschaltete Pipeline trägt es in Sekunden weiter.

- Wo jede Verbindung stehen blieb, bewahrt DataPlayer auf; Coinbase nicht.
- **Erster Lauf liest**: **Nur das Neue** beginnt jetzt; **Ab dem frühesten
  Verfügbaren** beginnt mit den neuesten tausend Trades oder dem letzten Tag
  an Kerzen.
- Eine Kerze wird gelesen, sobald ihr Intervall vorbei ist.
- Coinbase bewahrt jeden Trade auf, darum verpasst eine Verbindung, die lange
  nicht lief, keinen.
- Eine Tabelle, die die Verbindung anlegt, hat den Schlüssel **id** des
  Trades oder **open_time** der Kerze, also kommt nichts doppelt.

## Börse

- **Status**: der Endpunkt und ob Coinbase antwortet.
- **Uhr**: die Zeit von Coinbase und wie weit sie dem DataPlayer-Server
  voraus ist.
- **Anfragelimit**: was Coinbase dieser Adresse in einer Sekunde erlaubt, was
  verbraucht wurde, wo DataPlayer anhält und ob Anfragen zurückgehalten
  werden.
- **Märkte**: wie viele Produkte gehandelt werden, in wie vielen
  Kurswährungen und wann die Liste gelesen wurde; nach einer Stunde wird sie
  neu gelesen.

## Dashboards und Suche

- Das Dashboard **Coinbase-Verbindung** zeichnet die Anfragen je Sekunde
  gegenüber der Grenze von DataPlayer, wie lange Coinbase antwortet und ob es
  antwortet. Preise stehen nicht darauf: tragen Sie sie per Pipeline in eine
  Tabelle und zeichnen Sie diese.
- Die Suche findet Produkte nach Name und Asset: `eth` findet ETH-USD und
  ETH-BTC. Eine Suche in einer Kurswährung bleibt darin. Produkte können für
  die Suche über alles aufbewahrt werden.

## Das Anfragelimit

Coinbase erlaubt einer Adresse zehn öffentliche Anfragen je Sekunde.
DataPlayer zählt seine Anfragen selbst und hält bei vier je Sekunde an, sodass
es nie acht in einer beliebigen Sekunde überschreitet; eine Anfrage darüber
wartet auf die nächste Sekunde, statt zu scheitern, darum dauert ein langer
Download ein paar Sekunden länger. Weist Coinbase die Adresse trotzdem ab,
warten Anfragen eine Sekunde.
