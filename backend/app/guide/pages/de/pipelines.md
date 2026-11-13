# Pipelines

Eine Pipeline ordnet Ihre Verbindungen auf einer Arbeitsfläche an und zieht Verknüpfungen
zwischen dem, was sie enthalten: Zeilen einer Tabelle, die in eine andere Tabelle kopiert
werden, eine Tabelle, die als CSV-Datei in einen Ordner gespeichert wird, ein Topic, das in
eine Tabelle gelesen wird, und so weiter. Eine Pipeline läuft, wenn Sie **Ausführen** drücken, nach
einem Zeitplan oder — für eine Verknüpfung, die ein Topic oder eine Warteschlange liest —
fortlaufend.

Pipelines finden Sie im Bereich **Pipelines** des Schalters oben in der linken Leiste. Eine
Pipeline gehört nur Ihnen; sie wird nicht geteilt.

## Eine Pipeline erstellen

1. **Eine Pipeline erstellen** oder **Neu** neben dem Pipeline-Wechsler in der Kopfzeile. Sie
   erhält einen Namen; der Stift benennt sie um.
2. Ziehen Sie eine Verbindung aus der Liste links auf die Arbeitsfläche oder drücken Sie
   darauf. Ein Fenster mit ihrem Katalog öffnet sich mit Häkchen.
3. Setzen Sie Häkchen bei dem, was die Pipeline übernimmt — Tabellen, Dateien, Topics,
   Schlüssel — oder bei einem Ort, an dem Dinge ankommen sollen: ein Schema, ein Ordner, die
   oberste Ebene Ihres Speichers. Die Häkchen bleiben erhalten, wenn Sie in eine andere Ebene
   wechseln.
4. **Auf die Arbeitsfläche platzieren**. Was angehakt wurde, wird zu einer Karte: die Verbindung in ihrem
   Kopf und eine Zeile für jedes angehakte Element.

Eine Verbindung kann mehrere Karten haben. Eine Karte wird von Hand verschoben. Das Zahnrad in
ihrem Kopf oder ein Doppelklick öffnet das Fenster erneut, um den Inhalt zu ändern; ihr Kreuz
nimmt sie aus der Pipeline. An der Verbindung selbst ändert sich nichts.

Eine Karte, deren Verbindung nicht mehr existiert, nicht mehr mit Ihnen geteilt oder
ausgeschaltet ist, wird gestrichelt und sagt das. Eine Tabelle, die es nicht mehr gibt, ist
durchgestrichen und als „not found“ markiert.

## Verknüpfungen

- Ziehen Sie eine Zeile einer Karte auf eine Zeile einer anderen. Wenn etwas von der einen zur
  anderen gehen kann, wird eine Verknüpfung gezeichnet; wenn nicht, sagt die Karte warum.
- **Die Verbindungen anzeigen, die gezogen werden könnten** im Kopf zeichnet alle Verknüpfungen gestrichelt, die
  zwischen den Zeilen auf der Arbeitsfläche möglich wären, beschriftet nach dem, was sie täten.
  Ein Klick auf eine gestrichelte Verknüpfung zieht sie.
- Beide Enden einer Verknüpfung müssen in verschiedenen Verbindungen liegen: Innerhalb einer
  Verbindung verwenden Sie **Kopieren** und **Einfügen** in ihrem Katalog.

Wenn Sie eine Verknüpfung auswählen, öffnet sich ihr Feld unter der Arbeitsfläche: was sie tut,
eine Auswahl **Operation**, wenn mehrere passen, und deren eigene Optionen — ein **Dateiname**
und was bei **Wenn der Name vergeben ist** geschehen soll (**Anhalten und melden**, **Beide behalten**,
**Ersetzen**), die Tabelle, in die geschrieben wird, und wie ihre Spalten zu den Zeilen
passen, oder die Spalten von **Eine neue Tabelle**. Eine Verknüpfung, die in Schlüssel von Redis
schreibt, wird unter **Schlüssel und Werte** eingerichtet: welche Spalte jeden Schlüssel benennt,
was ihm vorangestellt wird und wie lange ein Schlüssel lebt.

Jede Verknüpfung erhält eine Nummer in der Reihenfolge, in der sie läuft. Eine Verknüpfung wartet
auf jede Verknüpfung, die in die Karte schreibt, aus der sie liest.

## Ausführen

- **Ausführen** speichert die Pipeline und führt jede Verknüpfung nacheinander aus. Fehlt einer
  Verknüpfung noch eine Auswahl, verweigert es den Start, bevor etwas läuft, und öffnet diese
  Verknüpfung.
- Die erste Verknüpfung, die fehlschlägt, stoppt den Lauf; die Verknüpfungen danach laufen nicht.
- Während des Laufs zeigt jede Verknüpfung **Wartet**, **Wird ausgeführt**, **Fertig** oder **Fehlgeschlagen**.
  Der Lauf erscheint in der Aktivitätsglocke, wo er gestoppt werden kann. Ein Stopp beendet die
  gerade laufende Verknüpfung; die folgenden laufen nicht.
- Was durch eine Verknüpfung fließt, läuft mit Ihren Rechten in diesem Moment. Eine Verbindung,
  die Sie nicht mehr erreichen, lässt ihre Verknüpfung fehlschlagen.

## Zeitplan

Die Uhr im Kopf öffnet **Zeitplan**: **Selbstständig ausführen** und dann entweder **In Abständen** — eine
Anzahl von Minuten, Stunden oder Tagen — oder **Zu Tageszeiten** an den angehakten Wochentagen.
Die Zeiten sind die Uhrzeit des Browsers, der den Zeitplan gespeichert hat. Der Kopf zeigt den
nächsten Lauf.

## Einem Topic oder einer Warteschlange folgen

Eine Verknüpfung, die ein Kafka-Topic, einen RabbitMQ-Stream oder eine Warteschlange oder eine
andere Nachrichtenquelle liest, kann in ihrem Feld mit **Folgen** markiert werden. **Der erste Lauf liest** wählt **Ab dem Frühesten, das verfügbar ist** oder **Nur Neues**; danach liest die
Verknüpfung dort weiter, wo sie aufgehört hat.

Der Schalter **Folgen** im Kopf übernimmt dann, was innerhalb von Sekunden eintrifft, bis er
ausgeschaltet wird. Während des Folgens zeigt die Aktivitätsglocke, wie viele Nachrichten
übernommen wurden; eine Verknüpfung, die immer wieder fehlschlägt, steht unter **Braucht dich**.

## Verlauf

**Verlauf** im Kopf listet jeden Lauf auf, der neueste zuerst: wann er begann, ob von Hand oder
nach dem Zeitplan, wie lange er dauerte und was jede Verknüpfung tat. Die Auswahl eines Laufs
zeigt ihn auf der Arbeitsfläche; **Zurück zur letzten Ausführung** kehrt zurück.

## Grenzen

- 100 Pipelines pro Person, 50 Karten pro Pipeline, 100 Zeilen pro Karte, 200 Verknüpfungen pro
  Pipeline.
- Das Löschen einer Pipeline entfernt ihre Karten und ihren Verlauf. An den Verbindungen ändert
  sich nichts.
