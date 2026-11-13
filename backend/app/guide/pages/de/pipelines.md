# Pipelines

Eine Pipeline legt Ihre Verbindungen auf einer Fläche aus und zieht Verbindungen
zwischen dem, was sie enthalten: Zeilen einer Tabelle, die in eine andere kopiert
werden, eine Tabelle, die als CSV-Datei in einem Ordner gespeichert wird, ein
Topic, das fortlaufend in eine Tabelle gelesen wird, und so weiter.
Eingeschaltet läuft sie von selbst: Eine Verbindung, die ein Topic, eine
Warteschlange oder einen Stream liest, überträgt Eintreffendes innerhalb von
Sekunden, die übrigen laufen nach Zeitplan. Sie lässt sich auch einmal von Hand
ausführen.

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

- Ziehen Sie eine Zeile einer Karte auf eine Zeile einer anderen. Während Sie
  ziehen, ist jede Zeile, auf die sie passt, getönt und sagt, was ein Ablegen
  dort täte; die übrigen sind abgeblendet und sagen, warum nicht. Auf einer
  getönten Zeile abgelegt, entsteht die Verbindung.
- Eine Verbindung wird startbereit gezeichnet, wo sich ihre Einstellungen
  erraten lassen: Eine neue Tabelle heißt nach ihrer Quelle und erhält all ihre
  Spalten, Spalten werden nach Namen gepaart, Schlüssel kommen aus dem
  Schlüssel eines Topics. Ihr Feld ändert jede davon.
- Eine Verbindung, der noch eine Wahl fehlt, wird in der Warnfarbe gezeichnet
  und sagt, was sie braucht. Die Zeile unter der Fläche nennt sie, und
  **Auswählen** öffnet sie.
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

## Einschalten

**Einschalten** im Kopf speichert die Pipeline und startet sie. Eine
Verbindung, die ein Topic, eine Warteschlange oder einen Stream liest, läuft
fortlaufend: Sie überträgt Eintreffendes innerhalb von Sekunden. Jede andere
Verbindung läuft nach Zeitplan. **Ausschalten** stoppt beides.

- Einschalten verweigert, bevor etwas startet, wenn einer Verbindung eine Wahl
  fehlt, und öffnet diese Verbindung; laufen Verbindungen nach Zeitplan und ist
  keiner festgelegt, öffnet es **Zeitplan…**.
- Die Zeile unter der Fläche sagt, was der Pipeline fehlt oder was sie tut:
  was das Einschalten bewirkt, wie lange sie schon eingeschaltet ist und wann
  sie zuletzt etwas übertragen hat, wann der Zeitplan als Nächstes kommt oder
  welche Verbindung immer wieder fehlschlägt.
- Eine Verbindung, die fortlaufend liest, kann stattdessen nach Zeitplan laufen:
  **Solange die Pipeline eingeschaltet ist** in ihrem Feld. **Der erste Lauf
  liest** wählt **Ab dem Frühesten, das verfügbar ist** oder **Nur Neues**;
  danach liest die Verbindung dort weiter, wo sie aufgehört hat.
- Solange sie eingeschaltet ist, zeigt die Aktivitätsglocke, wie viele
  Nachrichten übertragen wurden, und eine Verbindung, die immer wieder
  fehlschlägt, steht unter **Braucht dich**. Dort angehalten, wird die Pipeline
  ausgeschaltet.

## Einmal ausführen

- **Jetzt einmal ausführen** im Menü neben **Einschalten** speichert die
  Pipeline und führt jede Verbindung einmal aus, eine nach der anderen. Fehlt
  einer Verbindung noch eine Wahl, verweigert es vor dem Start und öffnet diese
  Verbindung. Solange die Pipeline eingeschaltet ist, bleiben fortlaufende
  Verbindungen außen vor.
- Die erste Verknüpfung, die fehlschlägt, stoppt den Lauf; die Verknüpfungen danach laufen nicht.
- Während des Laufs zeigt jede Verknüpfung **Wartet**, **Wird ausgeführt**, **Fertig** oder **Fehlgeschlagen**.
  Der Lauf erscheint in der Aktivitätsglocke, wo er gestoppt werden kann. Ein Stopp beendet die
  gerade laufende Verknüpfung; die folgenden laufen nicht.
- Was durch eine Verknüpfung fließt, läuft mit Ihren Rechten in diesem Moment. Eine Verbindung,
  die Sie nicht mehr erreichen, lässt ihre Verknüpfung fehlschlagen.

## Zeitplan

**Zeitplan…** im Menü neben **Einschalten** legt fest, wann die Verbindungen
nach Zeitplan laufen, solange die Pipeline eingeschaltet ist: entweder **In
Abständen** — eine Anzahl Minuten, Stunden oder Tage — oder **Zu Tageszeiten**
an den markierten Tagen. Die Zeiten folgen der Uhr des Browsers, der den
Zeitplan gespeichert hat. Die Zeile unter der Fläche zeigt den nächsten Lauf.

## Verlauf

**Verlauf** im Menü **⋯** des Kopfes listet jede Ausführung, die neueste zuerst:
wann sie begann, ob von Hand oder nach Zeitplan, wie lange sie dauerte und was
jede Verbindung getan hat. Eine gewählte Ausführung wird auf der Fläche gezeigt;
**Zurück zur letzten Ausführung** kehrt zurück.

## Grenzen

- 100 Pipelines pro Person, 50 Karten pro Pipeline, 100 Zeilen pro Karte, 200 Verknüpfungen pro
  Pipeline.
- Das Löschen einer Pipeline entfernt ihre Karten und ihren Verlauf. An den Verbindungen ändert
  sich nichts.
