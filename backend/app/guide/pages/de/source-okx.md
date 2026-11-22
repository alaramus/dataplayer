# OKX

Die öffentlichen Marktdaten von OKX: Spot, USDT- und USDC-Futures und
inverse Futures, unbefristet und mit Fälligkeit. Sie sehen den letzten Tag
und die Regeln jedes Symbols, lesen seine Kerzen, seine Trades der letzten
drei Monate und sein Orderbuch als Zeilen und beobachten seinen Markt live.
Auf OKX wird nichts geändert, und kein Schlüssel ist nötig. Wie Verbindungen
allgemein funktionieren, steht auf der Seite [Verbindungen](connections.md).

## Was Sie sehen können

- Spot, USDT- und USDC-Futures, inverse Futures, Symbole nach Kurswährung
- Die letzten 24 Stunden jedes Symbols: Preis, Änderung, Hoch, Tief, Volumen
- Die Handelsregeln jedes Symbols: Preisschritt und Mengenschritt
- Die Kerzen eines Symbols in jedem Intervall, von einer Sekunde bis zum Monat
- Die Trades eines Symbols der letzten drei Monate, nach Nummer oder Zeit
- Das Orderbuch eines Symbols, Gebote und Angebote mit laufender Summe
- Den Markt eines Symbols live: Chart, Orderbuch und Trades auf einem Schirm
- Jedes davon als Datei heruntergeladen
- Die Uhr von OKX, seine Wartung und wie viel jedes Limits verbraucht ist
- Die Limits und die Antworten von OKX auf einem Dashboard
- Symbole, nach Name oder Asset gefunden
- Trades oder Kerzen eines Symbols in einer Pipeline, je Lauf nur das Neue
- Mit Schlüssel: Guthaben, Positionen, Orders, eigene Trades, Ein-/Auszahlungen

## Was Sie ändern können

- Nichts: Marktdaten werden nur gelesen

## Verbinden

Die Seite **Verbindung** des Fensters fragt nach dem **Endpunkt**:

- **OKX** — `www.okx.com` und seine Streams auf `ws.okx.com`;
- **OKX Europe** — `eea.okx.com`, der europäische Dienst von OKX: ein eigener
  Markt mit eigenen Preisen und Trades;
- **Demohandel** — der Demomarkt von OKX mit eigenen Preisen.
- **OKX, mit einem API-Schlüssel**, **OKX Europe, mit einem API-Schlüssel**
  und **Demohandel, mit einem API-Schlüssel** — dasselbe und dazu das Konto,
  dem der Schlüssel gehört. Sie fragen nach dem Schlüssel, seinem Geheimnis
  und der Passphrase, die beim Anlegen des Schlüssels gewählt wurde.

OKX bedient manche Länder nicht, darunter die USA. Sagt die Prüfung, OKX
bediene diese Adresse oder Region nicht, steht der DataPlayer-Server in einem
davon; OKX Europe bedient nur den Europäischen Wirtschaftsraum.

## Der Katalog

- **Börse** zuerst: was OKX und diese Verbindung über sich sagen.
- **Märkte**: ein Ordner je Markt mit dessen Symbolen. Eine Zeile öffnet
  sofort ihren Chart **Markt**.
- **Spot**, **USDT- und USDC-Futures** und **Inverse Futures**. Die Futures
  enthalten die unbefristeten Swaps und die befristeten Futures von OKX
  zusammen. Jeder Markt enthält **Ticker**, **Symbole** und einen Ordner je
  Kurswährung, die mit den meisten Symbolen zuerst.
- Eine Kurswährung enthält ihre Symbole, nur die gerade gehandelten. Ein
  unbefristeter endet auf `-SWAP`, etwa `BTC-USDT-SWAP`; ein befristeter auf
  sein Datum, etwa `BTC-USDT-261225`.
- Ein Symbol enthält **Markt**, **Kerzen** mit einer Reihe je Intervall,
  **Trades** und **Orderbuch**.

## Markt

**Markt**, der erste Knoten jedes Symbols, öffnet einen Tab, der sich mit
dem Markt bewegt: der Tag oben, Kerzen über ihrem Volumen, das Orderbuch mit
der Tiefe jeder Stufe und die Trades, wie sie geschehen.

- Das Kerzenintervall wählen Sie oben; scrollen oder ziehen Sie den Chart,
  um zurückzublicken.
- Nach dem ersten Moment kommt alles aus den Streams von OKX, die nichts von
  seinen Limits kosten. Mehrere Tabs eines Symbols teilen sie.
- Fällt das Netz aus, sagt der Tab es und kommt von selbst zurück.

## Tabellen

- **Ticker**: eine Zeile je Symbol, die umsatzstärksten zuerst. Jede Spalte
  sortiert und filtert. Wird alle zehn Sekunden aufgefrischt. Für USDT- und
  USDC-Futures gibt OKX kein Kursvolumen, dort fehlt die Spalte, und die
  umsatzstärksten sind die mit dem meisten Volumen in der Münze.
- **Symbole**: eine Zeile je Symbol mit seinen Regeln. Futures ergänzen den
  Typ von OKX — `SWAP` für einen unbefristeten, `FUTURES` für einen
  befristeten —, die Fälligkeit eines befristeten und das Listungsdatum.
  Inverse Futures ergänzen, was ein Kontrakt in USD wert ist.
- **Kerzen**: die neuesten zuerst; nach **open_time** sortiert beginnt es mit
  den ältesten, ein Filter darauf wählt, wo das Lesen beginnt und endet. Die
  noch offene Kerze sagt `closed` false. Tage und Wochen öffnen um
  Mitternacht UTC.
- **Trades**: die neuesten zuerst. OKX nummeriert die Trades eines Symbols
  der Reihe nach und bewahrt sie drei Monate auf: ein Filter auf **id** oder
  **time** wählt, wo Sie schauen, und nach **id** sortiert beginnt es mit den
  ältesten.
- **Orderbuch**: Gebote vom besten an, dann Angebote vom besten an. Ein Filter
  auf **level** wählt die Tiefe, bis 400; 100 Stufen ohne Filter. Ein Filter
  auf **side** behält eine Seite.
- **volume** ist immer im Basis-Asset, **quote_volume** in der Kurswährung.
  OKX zählt Futures in Kontrakten; DataPlayer nennt jeden mit seinem Wert.
  Bei inversen Futures ist die Größe eines Trades in USD, darum heißt die
  Spalte dort **quote_quantity**, und auch die Menge im Orderbuch ist in USD.
- Preise und Mengen sind exakte Dezimalzahlen, wie OKX sie schreibt.

## In einer Pipeline

Die **Trades** eines Symbols und jede **Kerzen**-Reihe können eine
weiterlesende Verbindung einer Pipeline beginnen: **Neue Nachrichten an eine
Tabelle anhängen** oder **an eine neue Tabelle**, oder **Das Neueste je
Schlüssel behalten**. Jeder Lauf liest nur, was seit dem letzten kam, und
eine eingeschaltete Pipeline trägt es in Sekunden weiter.

- Wo jede Verbindung stehen blieb, bewahrt DataPlayer auf; OKX nicht.
- **Erster Lauf liest**: **Nur das Neue** beginnt jetzt; **Ab dem frühesten
  Verfügbaren** beginnt mit der letzten Stunde an Trades oder dem letzten Tag
  an Kerzen.
- Eine Kerze wird gelesen, sobald sie geschlossen ist.
- Eine Verbindung, die länger als drei Monate nicht lief, findet ihre
  ältesten Trades bei OKX gelöscht; der Lauf sagt, wie viele übersprungen
  wurden.
- Eine Tabelle, die die Verbindung anlegt, hat den Schlüssel **id** des
  Trades oder **open_time** der Kerze, also kommt nichts doppelt.

## Ihr Konto

Mit einem Schlüssel enthält jeder Markt **Konto**: **Guthaben** des
Handelskontos, in jedem Markt dieselben; **Positionen** bei Futures;
**Offene Orders**; und bei Spot **Einzahlungen** und **Auszahlungen**. Ein
Symbol ergänzt **Meine Orders** der letzten sieben Tage und **Meine Trades**
der letzten drei. **Meine Trades** können eine Verbindung einer Pipeline
beginnen, wie **Trades**.

- Legen Sie den Schlüssel bei OKX nur mit der Berechtigung **Read** an. Ein
  Schlüssel, der auch handeln oder auszahlen darf, wird angenommen, und die
  Prüfung sagt es: DataPlayer liest nur, aber ein Schlüssel nur zum Lesen ist
  sicherer.
- Ist der Schlüssel auf Adressen beschränkt, fügen Sie die des
  DataPlayer-Servers hinzu.
- **API-Schlüssel** unter **Börse** sagt, was OKX dem Schlüssel erlaubt.

## Börse

- **Status**: der Endpunkt, ob OKX eine Wartung des Handels meldet und ob
  jeder Markt antwortet.
- **Uhr**: die Zeit jedes Marktes und wie weit sie dem DataPlayer-Server
  voraus ist.
- **Anfragelimit**: für jede Art bisher gestellter Anfragen, was OKX in
  ihrem Fenster erlaubt, was verbraucht wurde, wo DataPlayer anhält und ob
  Anfragen zurückgehalten werden.
- **Märkte**: wie viele Symbole gehandelt werden, in wie vielen
  Kurswährungen und wann die Liste gelesen wurde; nach einer Stunde wird sie
  neu gelesen.
- **API-Schlüssel**: ob der Schlüssel nur liest, ob er handeln oder
  auszahlen darf und ob er auf Adressen beschränkt ist.

## Dashboards und Suche

- Das Dashboard **OKX-Verbindung** zeichnet die Anfragen jeder Art in ihrem
  Fenster gegenüber der Grenze von DataPlayer, wie lange OKX antwortet und ob
  jeder Markt antwortet. Preise stehen nicht darauf: tragen Sie sie per
  Pipeline in eine Tabelle und zeichnen Sie diese.
- Die Suche findet Symbole nach Name und Asset: `btc` findet BTC-USDT und
  ETH-BTC, Namen zuerst. Eine Suche in einer Kurswährung bleibt darin.
  Symbole können für die Suche über alles aufbewahrt werden.

## Das Anfragelimit

OKX begrenzt jede Art von Anfrage für sich: so viele in zwei Sekunden — 20
für Kerzen, 20 für Trades, 40 für das Orderbuch. DataPlayer zählt seine
Anfragen selbst und hält bei 40 % jeder Grenze an, sodass es nie 80 %
beliebiger zwei Sekunden überschreitet; eine Anfrage darüber wartet auf die
nächsten zwei Sekunden, statt zu scheitern, darum dauert ein langer Download
ein paar Sekunden länger. Weist OKX die Adresse trotzdem ab, wartet diese Art
von Anfrage zwei Sekunden.
