# Der Arbeitsbereich

Im Bereich **Daten** werden Verbindungen geöffnet und ihr Inhalt gelesen. Was die anderen
Bereiche sind, steht auf [DataPlayer auf einen Blick](overview.md).

## Drei Spalten

- **Verbindungen**, links: alle Verbindungen, die Ihnen gehören oder mit Ihnen geteilt
  wurden. Ein Klick öffnet ihren Katalog. Siehe [Verbindungen](connections.md).
- **Catalogs**, in der Mitte: was jede geöffnete Verbindung enthält, Ebene für Ebene. Das
  Filterfeld oben grenzt die Ebene nach Namen ein; seine Suchschaltfläche sucht einen
  Namen überall darunter. **Katalog daneben duplizieren** öffnet eine zweite Kopie
  desselben Katalogs.
- **Work**, rechts: die Tabellen, Dateien, Abfragen, Strukturen und Diagramme, die aus
  einem Katalog geöffnet wurden, jeweils in einem Tab. Solange sie leer ist, sagt sie,
  was als Nächstes zu tun ist.

Spalten ändern ihre Breite, wenn Sie die Linie zwischen ihnen ziehen. Das Layout, das Sie
hinterlassen, finden Sie beim nächsten Mal wieder.

## Tabs

- Ein Tab wird wie ein Browser-Tab gezogen: Auf den Tabs einer anderen Spalte abgelegt,
  verbindet er sich mit ihnen; auf dem Inhalt einer Spalte abgelegt, teilt er diese in zwei.
  Ein Tab kann nur in eine Spalte wandern, die seine Art annimmt.
- **Im Katalog anzeigen** findet den Knoten eines Tabs in seinem Katalog.
- **In einem Fenster öffnen** löst einen Tab in ein schwebendes Fenster heraus, und **Als Tab öffnen** setzt ihn zurück.
- **Die anderen Tabs schließen**, eine Schaltfläche am Ende der Tabs einer Spalte, schließt alle
  außer dem angezeigten.
- Die Markierung neben einer Schaltfläche zum Neuladen zeigt **Live**, wenn das Angezeigte
  gerade von der Quelle gelesen wurde, und eine Uhr, wenn es eine gespeicherte Antwort ist.
  Wenn Sie darauf zeigen, sehen Sie, wie alt sie ist.

Ein Abschnitt des Layouts kann beiseitegelegt werden: Er verschwindet vom Bildschirm und
wartet als Schaltfläche in **Beiseitegelegte Abschnitte** am Fuß, die ihn zurückbringt.

## Tab-Gruppen

Die Tabs, die in Data geöffnet sind, und die Anordnung der Spalten lassen sich unter einem
Namen speichern.

- **Gruppe speichern** auf der rechten oberen Leiste speichert, was jetzt geöffnet ist.
- **Gespeicherte Tab-Gruppen** daneben listet sie auf. Das Öffnen einer Gruppe ersetzt die offenen
  Tabs und fragt vorher nach.
- **Gruppe verwalten** benennt eine Gruppe um, löscht sie oder aktualisiert sie aus dem jetzt
  offenen Layout. Das Löschen einer Gruppe schließt keine Tabs.

## Schwebende Fenster

Die Einstellungen einer Verbindung, Formulare, Fragen und herausgelöste Tabs öffnen sich in
schwebenden Fenstern; mehrere können gleichzeitig offen sein. DataPlayer blockiert den
übrigen Bildschirm nicht.

- Ein Fenster wird an seiner Leiste verschoben, an seinen Rändern in der Größe geändert und
  hat **Minimieren**, **Maximieren** und **Fenster schließen**.
- Ein Fenster mit Formular schließt sich nur über sein Kreuz, damit ein Druck auf Esc nie
  Eingetipptes verliert. Eine Frage schließt sich ebenfalls mit Esc.
- Ein minimiertes Fenster wartet unter **Offene Fenster** am Fuß des Bildschirms.

## Zwei Verbindungen nebeneinander

**Mit einer anderen Verbindung paaren** im Kopf eines Katalogs legt die Kataloge zweier Verbindungen
in ein Fenster, um Dinge zwischen ihnen zu verschieben: Es zeigt, was von einer zur anderen
gehen kann, und **Seiten tauschen** kehrt die Richtung um. **Dieses Paar vergessen** schließt sie.

## Aktivität und Benachrichtigungen

Die Aktivitätsglocke unten rechts öffnet **Aktivität** mit drei Abschnitten:

- **Braucht dich**: was auf Ihre Antwort wartet — eine Frage des Agenten, eine Anfrage nach
  Zugriff auf Ihre Verbindung, eine Verbindung, die nicht mehr antwortet, ein fehlgeschlagener
  Auftrag;
- **Wird ausgeführt**: was der Server für Sie tut — Kopien, Sicherungen, Pipeline-Läufe, das Starten
  von Diensten, Suchen in Dateien. Lange Arbeit lässt sich hier anhalten oder stoppen, wo
  es der Typ erlaubt;
- **Zuletzt**: was zuletzt angefallen ist. **Alle löschen** leert ihn.

Kurze Hinweise erscheinen als Karten unten rechts und landen unter **Zuletzt**. **Nicht stören** unterdrückt die Karten; alles bleibt in Activity.
