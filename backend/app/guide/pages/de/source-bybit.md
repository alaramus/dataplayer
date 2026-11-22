# Bybit

Die öffentlichen Marktdaten von Bybit: Spot, USDT- und USDC-Futures und
inverse Futures. Sie sehen den letzten Tag und die Handelsregeln jedes
Symbols, lesen seine Kerzen, neuesten Trades und sein Orderbuch als Zeilen
und verfolgen seinen Markt live. Auf Bybit wird nichts geändert, und kein
Schlüssel wird gebraucht. Wie Verbindungen allgemein funktionieren, steht auf
der Seite [Verbindungen](connections.md).

## Was Sie sehen können

- Spot, USDT- und USDC-Futures, inverse Futures, Symbole nach Kurswährung
- Die letzten 24 Stunden jedes Symbols: Preis, Änderung, Hoch, Tief, Volumen
- Die Handelsregeln jedes Symbols: Preisschritt, Mengenschritt, Mindestorder
- Die Kerzen eines Symbols in jedem Intervall, von einer Minute bis zum Monat
- Die neuesten Trades eines Symbols: 60 bei Spot, 1.000 bei Futures
- Das Orderbuch eines Symbols, Gebote und Angebote mit laufender Summe
- Der Markt eines Symbols live: Chart, Orderbuch und Trades auf einem Schirm
- Alles davon als Datei heruntergeladen
- Die Uhr von Bybit und wie viel vom Anfragelimit verbraucht ist
- Das Anfragelimit und die Antworten von Bybit auf einem Dashboard
- Symbole nach Name oder Asset gefunden
- Trades oder Kerzen eines Symbols in einer Pipeline, je Lauf nur das Neue
- Mit Schlüssel: Guthaben, Positionen, Orders, eigene Trades, Ein-/Auszahlungen

## Was Sie ändern können

- Nichts: Marktdaten werden nur gelesen

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach dem **Endpunkt**:

- **Bybit** — `api.bybit.com` und seine Streams auf `stream.bybit.com`;
- **Bybit, über bytick.com** — derselbe Dienst unter seinem zweiten Namen,
  für ein Netz, das den ersten nicht erreicht;
- **Testnetz** — das Testnetz von Bybit mit eigenen Preisen.
- **Bybit, mit einem API-Schlüssel** und **Testnetz, mit einem
  API-Schlüssel** — dieselben Hosts und dazu das einheitliche Konto, dem der
  Schlüssel gehört.

Bybit bedient einige Länder nicht, darunter die USA. Sagt die Prüfung, Bybit
bediene diese Region nicht oder lehne diese Adresse ab, steht der
DataPlayer-Server in einem davon, und ein anderer Endpunkt hilft nicht.

## Der Katalog

- Zuerst **Börse**: was Bybit und diese Verbindung über sich sagen.
- **Märkte**: ein Ordner je Markt mit dessen Symbolen. Eine Zeile öffnet
  sofort ihren **Markt**-Chart.
- **Spot**, **USDT- und USDC-Futures** und **Inverse Futures**. Jeder enthält
  **Ticker**, **Symbole** und einen Ordner je Kurswährung, die mit den
  meisten Symbolen zuerst.
- Eine Kurswährung enthält ihre Symbole, nur die jetzt gehandelten.
  Terminfutures tragen ihre Lieferung im Namen, etwa `BTCUSDT-27NOV26`.
- Ein Symbol enthält **Markt**, **Kerzen** mit einer Reihe je Intervall,
  **Trades** und **Orderbuch**.

## Markt

**Markt**, der erste Knoten jedes Symbols, öffnet einen Tab, der sich mit
dem Markt bewegt: der Tag oben, Kerzen über ihrem Volumen, das Orderbuch mit
der Tiefe jeder Stufe und die Trades, wie sie geschehen.

- Wählen Sie das Kerzenintervall oben; scrollen oder ziehen Sie den Chart,
  um zurückzublicken.
- Nach dem ersten Moment kommt alles aus den Streams von Bybit, die nichts
  vom Anfragelimit kosten. Mehrere Tabs eines Symbols teilen einen Stream.
- Fällt das Netz aus, sagt der Tab es und kommt von selbst zurück.

## Tabellen

- **Ticker**: eine Zeile je Symbol, die umsatzstärksten nach Kursvolumen
  zuerst. Jede Spalte sortiert und filtert. Alle zehn Sekunden neu.
- **Symbole**: eine Zeile je Symbol mit seinen Regeln. Futures ergänzen den
  Kontrakttyp von Bybit, das Lieferdatum eines Terminfutures und das
  Listungsdatum.
- **Kerzen**: die neuesten zuerst; nach **open_time** sortiert beginnt es mit
  den ältesten, ein Filter darauf wählt, wo das Lesen beginnt und endet. Die
  noch offene Kerze sagt `closed` false.
- **Trades**: nur die neuesten, die Bybit gibt — 60 bei Spot, 1.000 bei
  Futures, bei einem lebhaften Symbol weniger als eine Minute. Jede Spalte
  sortiert und filtert. Ältere Trades gibt Bybit nicht heraus.
- **Orderbuch**: Gebote vom besten an, dann Angebote vom besten an. Ein Filter
  auf **level** wählt die Tiefe, bis 1.000; standardmäßig 100 Stufen. Ein
  Filter auf **side** zeigt eine Seite.
- **volume** ist immer im Basis-Asset, **quote_volume** in der Kurswährung.
  Inverse Futures zählen in USD, und DataPlayer setzt jedes an seinen Platz.
- Preise und Mengen sind exakte Dezimalzahlen, wie Bybit sie schreibt.

## In einer Pipeline

Die **Trades** eines Symbols und jede **Kerzen**-Reihe können eine
weiterlesende Verbindung einer Pipeline beginnen: **Neue Nachrichten an eine
Tabelle anhängen** oder **an eine neue Tabelle**, oder **Das Neueste je
Schlüssel behalten**. Jeder Lauf liest nur, was seit dem letzten kam, und
eine eingeschaltete Pipeline trägt es in Sekunden weiter.

- Wo jede Verbindung stehen blieb, bewahrt DataPlayer auf; Bybit nicht.
- **Erster Lauf liest**: **Nur das Neue** beginnt jetzt; **Ab dem frühesten
  Verfügbaren** beginnt mit den Trades, die Bybit noch gibt, oder dem letzten
  Tag an Kerzen.
- Eine Kerze wird gelesen, sobald sie geschlossen ist.
- Bybit gibt nur seine neuesten Trades, darum verpasst eine Verbindung, die
  seltener läuft, als ein lebhaftes Symbol tausend Trades macht, einige; der
  Lauf sagt, dass Trades übersprungen wurden. Schalten Sie die Pipeline ein,
  um sie zu tragen, wie sie kommen.
- Eine Tabelle, die die Verbindung anlegt, hat den Schlüssel **id** des
  Trades oder **open_time** der Kerze, also kommt nichts doppelt.

## Ihr Konto

Mit einem Schlüssel enthält jeder Markt **Konto**: **Guthaben** der
einheitlichen Wallet, in jedem Markt dieselben; **Positionen** bei Futures;
**Offene Orders**; und bei Spot **Einzahlungen** und **Auszahlungen** der
letzten dreißig Tage. Ein Symbol ergänzt **Meine Orders** und **Meine Trades**
der letzten sieben Tage. **Meine Trades** können eine Verbindung einer
Pipeline beginnen, wie **Trades**.

- Legen Sie den Schlüssel bei Bybit nur zum Lesen an. Ein Schlüssel, der auch
  handeln oder Geld bewegen darf, wird angenommen, und die Prüfung sagt es:
  DataPlayer liest nur, aber ein Schlüssel nur zum Lesen ist sicherer.
- Ist der Schlüssel auf Adressen beschränkt, fügen Sie die des
  DataPlayer-Servers hinzu.
- **API-Schlüssel** unter **Börse** sagt, was Bybit dem Schlüssel erlaubt.
- Auszahlungen werden nur dem Schlüssel des Hauptkontos beantwortet.

## Börse

- **Status**: der Endpunkt und ob jeder Markt antwortet.
- **Uhr**: die Zeit jedes Marktes und wie weit sie dem DataPlayer-Server
  voraus ist.
- **Anfragelimit**: was Bybit dieser Adresse in fünf Sekunden erlaubt, was
  verbraucht wurde, wo DataPlayer anhält und ob Anfragen zurückgehalten
  werden.
- **Märkte**: wie viele Symbole gehandelt werden, in wie vielen
  Kurswährungen, und wann die Liste gelesen wurde; nach einer Stunde erneut.
- **API-Schlüssel**: ob der Schlüssel nur liest, was Bybit ihm erlaubt und
  ob er auf Adressen beschränkt ist.

## Dashboards und Suche

- Das Dashboard **Bybit-Verbindung** zeichnet die Anfragen je fünf Sekunden
  gegenüber der Grenze von DataPlayer, wie lange Bybit antwortet und ob jeder
  Markt antwortet. Preise stehen nicht darauf: tragen Sie sie per Pipeline
  in eine Tabelle und zeichnen Sie diese.
- Die Suche findet Symbole nach Name und Asset: `btc` findet BTCUSDT und
  ETHBTC, Namen zuerst. Eine Suche in einer Kurswährung bleibt darin. Symbole
  können für die Suche über alles aufbewahrt werden.

## Das Anfragelimit

Bybit erlaubt einer Adresse 600 Anfragen in fünf Sekunden über alle Märkte
und sperrt eine Adresse, die mehr fragt, für mindestens zehn Minuten.
DataPlayer zählt seine Anfragen selbst und hält bei 240 in fünf Sekunden an
und sagt, wie lange zu warten ist. Sperrt Bybit die Adresse trotzdem, wird
nichts gefragt, bis die Sperre endet.
