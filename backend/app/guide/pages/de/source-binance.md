# Binance

Die öffentlichen Marktdaten von Binance: Spot, USDⓈ-M- und COIN-M-Futures. Sie sehen
den letzten Tag und die Handelsregeln jedes Symbols und lesen die Kerzen,
Trades und das Orderbuch eines Symbols als Zeilen. Auf Binance wird nichts
geändert, und kein Schlüssel ist nötig. Wie Verbindungen allgemein
funktionieren, steht auf der Seite [Verbindungen](connections.md).

## Was Sie sehen können

- Spot, USDⓈ-M- und COIN-M-Futures, die Symbole nach Quote-Asset
- Die letzten 24 Stunden jedes Symbols: Preis, Änderung, Hoch, Tief, Volumen
- Die Handelsregeln jedes Symbols: Preisschritt, Mengenschritt, Mindestorder
- Die Kerzen eines Symbols in jedem Intervall, von 1 Sekunde bis 1 Monat
- Die Trades eines Symbols, die neuesten zuerst, nach ID oder ab einer Zeit
- Das Orderbuch eines Symbols, Gebote und Angebote mit laufenden Summen
- Mit Schlüssel: Guthaben, Positionen, Orders, eigene Trades, Ein-/Auszahlungen
- Jede davon als Datei heruntergeladen
- Der Status von Binance, seine Uhr und wie viel vom Anfragelimit verbraucht ist
- Das Anfragelimit und die Antworten von Binance auf einem Dashboard
- Symbole nach Namen oder nach Asset gefunden
- Trades oder Kerzen eines Symbols per Pipeline übertragen, nur Neues je Lauf

## Was Sie ändern können

- Nichts: Marktdaten werden nur gelesen

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach dem **Endpunkt**:

- **Binance** — die Haupthosts, `api.binance.com`, `fapi.binance.com` und
  `dapi.binance.com`;
- **Binance, nur Marktdaten** — Spot von `data-api.binance.vision`, das nur
  öffentliche Daten liefert und oft antwortet, wenn der Haupthost ausgelastet
  ist;
- **Testnetz** — das Testnetz von Binance, mit eigenen Preisen.
- **Binance, mit API-Schlüssel** und **Testnetz, mit API-Schlüssel** — die
  gleichen Hosts, und dazu das Konto, dem der Schlüssel gehört.

Binance lehnt einige Länder ab. Sagt die Prüfung, dass Binance diese Adresse
nicht bedient, steht der DataPlayer-Server in einem davon, und ein anderer
Endpunkt hilft nicht.

## Der Katalog

- Zuerst **Börse**: was Binance und diese Verbindung über sich sagen.
- **Spot**, **USDⓈ-M-Futures** und **COIN-M-Futures**. Jeder enthält **Ticker**, **Symbole** und
  einen Ordner je Quote-Asset — **USDT**, **USDC**, **BTC** und die übrigen —,
  den mit den meisten Symbolen zuerst.
- Ein Quote-Asset enthält seine Symbole: nur die, die gerade gehandelt werden.
- Ein Symbol enthält **Kerzen** mit einer Serie je Intervall, **Trades** und
  **Orderbuch**.

## Tabellen

- **Ticker**: eine Zeile je Symbol, das umsatzstärkste nach Quote-Volumen
  zuerst. Jede Spalte sortiert und filtert. Aktualisiert sich alle zehn
  Sekunden.
- **Symbole**: eine Zeile je Symbol mit seinen Regeln. Futures ergänzen den
  Kontrakttyp, das Lieferdatum und das Datum der Listung.
- **Kerzen**: die neuesten zuerst; nach **open_time** sortieren beginnt bei
  den ältesten, und ein Filter darauf wählt, wo das Lesen beginnt und endet.
  Die noch offene Kerze hat `closed` false.
- **Trades**: die aggregierten Trades von Binance, die neuesten zuerst. Ein
  Filter nach **id** oder **time** wählt, wo das Lesen beginnt. Binance
  bewahrt Spot-Trades etwa zwei Jahre auf und liefert Futures-Trades nur der
  letzten zwei Tage.
- **Orderbuch**: zuerst die besten Gebote, dann die besten Angebote. Ein
  Filter auf **level** wählt die Tiefe, standardmäßig 100 Stufen. Ein Filter
  auf **side** behält eine Seite.
- Eine Seite mit Kerzen oder Trades reicht höchstens zehntausend Zeilen tief.
  Um weiter zurückzublicken, nach Zeit filtern.
- Preise und Mengen sind exakte Dezimalzahlen, wie Binance sie schreibt.
- **COIN-M** zählt in Kontrakten zu 100 USD bei BTC und 10 USD bei den
  übrigen. Ticker und Kerzen geben trotzdem **volume** im Basis-Asset und
  **quote_volume** in USD, wie jeder Markt; **Symbole** ergänzt
  **contract_size**. Die **quantity** eines Trades und des Orderbuchs sind
  Kontrakte.

## In einer Pipeline

Die **Trades** eines Symbols und jede Serie von **Kerzen** können der Anfang
einer Verbindung einer Pipeline sein, die weiterliest: **Neue Nachrichten zu
einer Tabelle hinzufügen** oder **zu einer neuen Tabelle**, oder **Das
Neueste je Schlüssel behalten**. Jeder Lauf liest nur, was seit dem letzten
kam, und **Folgen** überträgt es innerhalb von Sekunden.

- DataPlayer merkt sich, wo jede Verbindung stehen blieb; Binance nicht.
- **Der erste Lauf liest**: **Nur Neues** beginnt jetzt; **Ab dem Frühesten,
  das verfügbar ist** beginnt mit der letzten Stunde der Trades oder dem
  letzten Tag der Kerzen.
- Eine Kerze wird gelesen, sobald sie geschlossen ist.
- Eine Tabelle, die die Verbindung anlegt, erhält einen Schlüssel auf die
  **id** des Trades oder die **open_time** der Kerze, sodass nichts doppelt
  ankommt.
- Ticker, Symbole und das Orderbuch sind ein Moment, keine Geschichte: eine
  Verbindung nimmt sie bei jedem Lauf ganz.

## Ihr Konto

Mit einem Schlüssel enthält jeder Markt **Konto**: **Guthaben**,
**Positionen** bei Futures, **Offene Orders** und bei Spot **Einzahlungen**
und **Auszahlungen** der letzten neunzig Tage. Ein Symbol ergänzt **Meine
Orders** und **Meine Trades**, je die neuesten tausend. **Meine Trades**
kann eine Verbindung einer Pipeline beginnen, wie **Trades**.

- Erstellen Sie den Schlüssel bei Binance nur zum Lesen. Ein Schlüssel, der
  auch handeln oder abheben darf, wird angenommen, und die Prüfung sagt es:
  DataPlayer liest nur, aber ein Schlüssel nur zum Lesen ist sicherer.
- Ist der Schlüssel auf Adressen beschränkt, fügen Sie die des
  DataPlayer-Servers hinzu.
- **API-Schlüssel** unter **Börse** sagt, was Binance dem Schlüssel erlaubt.
- Das Testnetz vergibt eigene Schlüssel für Spot und Futures; eine
  Verbindung hält einen, also lehnt der andere Markt ihn ab.

## Börse

- **Status**: der Endpunkt, der eigene Status von Binance — nur auf dem
  Hauptendpunkt bekannt — und ob jeder Markt antwortet.
- **Uhr**: die Zeit jedes Marktes und wie weit sie dem DataPlayer-Server
  voraus ist. An Binance gesendete Zeiten sind die des Servers, ein großer
  Unterschied verschiebt sie.
- **Anfragelimit**: was jeder Markt je Minute erlaubt, was diese Adresse in
  dieser Minute verbraucht hat, wo DataPlayer anhält und ob Binance Anfragen
  zurückhält.
- **Märkte**: wie viele Symbole gehandelt werden, in wie vielen
  Quote-Assets, und wann die Liste gelesen wurde; nach einer Stunde wird sie
  erneut gelesen.

## Dashboards und Suche

- Das Dashboard **Binance-Verbindung** zeigt das je Minute verbrauchte
  Gewicht gegen die Schwelle von DataPlayer, wie schnell Binance antwortet und
  ob jeder Markt antwortet. Preise stehen nicht darauf: übertragen Sie sie per
  Pipeline in eine Tabelle und zeichnen Sie diese.
- Die Suche findet Symbole nach Namen und nach Asset: `btc` findet BTCUSDT
  und ETHBTC, Namen zuerst. Eine Suche innerhalb eines Quote-Assets bleibt
  darin. Symbole lassen sich für die Suche über alles behalten.

## Das Anfragelimit

Binance zählt, was jede Adresse je Minute anfragt, und sperrt eine Adresse,
die zu viel anfragt. DataPlayer liest den Zähler aus jeder Antwort und hält
bei 80 % des Limits an und sagt, wie viele Sekunden der Minute noch bleiben.
Sperrt Binance die Adresse trotzdem, wird bis zum Ende der Sperre nichts
angefragt.
