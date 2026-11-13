# Der KI-Agent

Der Agent antwortet im Bereich **KI** des Schalters oben in der linken Leiste. Er arbeitet über Ihre
Verbindungen wie Sie selbst: Er listet sie auf, findet und liest Tabellen und Dateien, führt Abfragen
und Aktionen aus, öffnet Dinge im Bereich Data, zeichnet Diagramme — und liest dieses Handbuch, um
Fragen zu DataPlayer selbst zu beantworten. Eine Änderung, die er vornehmen will, wird zuerst mit Ihnen
abgestimmt.

## Vor dem ersten Chat

Der Agent arbeitet mit Ihrem eigenen Schlüssel eines Modellanbieters: Anthropic, OpenAI, Google,
DeepSeek und andere.

1. Öffnen Sie den Bereich AI und **Einstellungen**.
2. Wählen Sie ein Modell. Das Schlüsselsymbol daneben öffnet den Schlüssel des Anbieters: einfügen,
   **Prüfen**, speichern. Ein Schlüssel gilt für alle Modelle dieses Anbieters.
3. Das in den Einstellungen gewählte Modell ist das, mit dem ein neuer Chat beginnt. Jeder Chat kann
   im eigenen Eingabefeld ein anderes wählen.

## Ein Chat

- **Neuer Chat** startet einen. Tippen Sie in **Nachricht an den Agenten** und klicken Sie auf **Senden**; wo der
  Browser zuhören kann, diktiert das Mikrofon stattdessen.
- Während der Agent arbeitet, werden seine Schritte einzeln angezeigt: was er gelesen, was er
  ausgeführt hat, wie lange es dauerte. **Stoppen** beendet die Antwort.
- Antworten sind formatierter Text mit Tabellen, Diagrammen und Schemata. Jede kann kopiert oder
  vorgelesen werden.
- Wenn Sie Wörter in einer Antwort markieren, erscheinen **Zum Chat hinzufügen**, das sie in Ihre nächste
  Nachricht zitiert, und **Weitere Details**, das den Schnell-Chat um eine Erklärung bittet.

## Was der Agent weiß

Der Agent sieht Ihren Bildschirm nicht. Um ihn auf etwas zu richten, nutzen Sie **Tabs oder Dateien anhängen**:

- **Arbeitsbereich-Tabs…**: bis zu fünf offene Tabs — eine Tabelle, ein Katalog, eine Abfrage, ein
  Ergebnis — für die nächste Nachricht;
- **Dateien vom Computer…**: Textdateien sowie PNG-, JPEG-, WebP- oder GIF-Bilder für ein Modell, das
  Bilder lesen kann.

Ohne Anhang findet er Dinge über den Namen mit der Suche. Wenn mehrere Verbindungen zu einem Namen
passen, fragt er, welche gemeint ist.

## Änderungen

**Änderungen** im Eingabefeld legt fest, was der Agent in diesem Chat ändern darf:

- **Nur Lesen**: aus diesem Chat wird nichts geändert;
- **Vor Änderungen fragen**, damit beginnt jeder Chat: Eine Änderung wartet auf Ihre Antwort auf einer
  Karte mit **Allow once**, **Allow all changes in this chat** und **Alle Änderungen in jedem Chat erlauben**.
  Die Karte zeigt, was sich ändern würde — die Anweisungen, und was ein Löschen mitnimmt;
- **Änderungen erlauben**: Änderungen in diesem Chat laufen ohne Nachfrage;
- **Jev entscheiden lassen**: Jev, ein eigener Dienst mit eigenem Schlüssel, entscheidet vor jeder Änderung;
- **Alle Änderungen in jedem Chat erlauben** ist eine Einstellung von Ihnen, nicht des Chats. Sie wird in
  **Einstellungen** unter **Bestätigungen** wieder ausgeschaltet.

Ein Chat, der auf Ihre Antwort wartet, steht unter **Braucht dich** in der Aktivitätsglocke. Eine
Verbindung, die für Konsolen auf **Nur Lesen** steht, wird nie beschrieben, und eine Zugriffsstufe, die
Sie nicht haben, wird nie benutzt.

## Welche Verbindungen er lesen darf

Der Agent liest eine Verbindung nur, wenn ihr Besitzer auf der Seite **Berechtigungen** der Verbindung
**Das Senden von Daten an Dritte erlauben** eingeschaltet hat: Was er liest, wird an den Modellanbieter
gesendet. Sonst sieht der Agent nur Name und Art der Verbindung und sonst nichts. Der Besitzer kann
dies aus dem abgelehnten Schritt erlauben; einer Person, mit der die Verbindung geteilt wird, wird
gesagt, dass sie den Besitzer fragen soll.

Wird die Einstellung später ausgeschaltet, verschwindet das aus dieser Verbindung Gelesene aus den
weiteren Antworten des Chats.

## Chats, Projekte und das Archiv

- Die Liste der Chats hat **Angeheftet** angeheftete Chats oben und einen Filter nach Namen.
- Ein Chat kann angeheftet, in ein Projekt verschoben, umbenannt und archiviert werden.
- **Neues Projekt** gruppiert Chats. Beim Löschen eines Projekts wird gefragt, ob seine Chats in die
  Liste oder ins Archiv zurückkehren sollen.
- **Archiv** in den Einstellungen stellt archivierte Chats wieder her oder löscht sie endgültig.

## Modellauswahl durch Jev

Statt eines Modells lässt **Mit Jev wählen** Jev für jede Antwort ein Modell aus den Modellen
wählen, für die Sie Schlüssel hinterlegt haben. Ihre Anfrage wird an TypeSafe gesendet, den Anbieter
von Jev, um die Wahl zu treffen. Dafür wird ein Jev-Schlüssel benötigt, der in den Einstellungen
hinterlegt wird.

## Schnell-Chat

**Schnellchat** oben in der linken Leiste öffnet ein Fenster für ein einfaches Gespräch mit einem Modell
aus jedem Bereich. Es hat keine Werkzeuge und kann nichts in DataPlayer lesen. In Chrome auf einem
Desktop-Rechner kann Gemini Nano antworten, das auf Ihrem eigenen Rechner läuft, sobald Chrome es
geladen hat; so verlässt nichts den Rechner. Schnell-Chats erscheinen im selben Verlauf wie die Chats
des Agenten.

## Werkzeuge externer MCP-Server

Der Agent kann auch die Werkzeuge von MCP-Servern aufrufen, die Sie hinzufügen: ein Ticketsystem, ein
Wiki, ein eigener Dienst.

1. Öffnen Sie den Bereich AI und **Einstellungen**, dann **Server hinzufügen** unter **Fremde MCP-Server**.
2. Geben Sie einen Namen und die Streamable-HTTP-Adresse an, etwa `https://mcp.example.com/mcp`.
   **Bearer-Token** und **Weitere Header** werden mit jeder Anfrage gesendet; nach dem Speichern werden
   sie nie wieder angezeigt, und ein leeres Feld behält den gespeicherten Wert.
3. **Werkzeuge** fragt den Server, was er anbietet. Jedes Werkzeug zeigt **Liest** oder **Fragt zuerst** und
   kann ausgeschaltet werden.

- Ein Werkzeug, das nicht sagt, dass es nur liest, gilt als Änderung: Es fragt vorher mit den Argumenten,
  die es senden würde; ein Chat mit **Nur Lesen** lehnt es ab, und **Änderungen erlauben** lässt es laufen.
- Das Serversymbol im Eingabefeld schaltet jeden Server für diesen Chat ein oder aus.
- Ein Server, der nicht antwortet, wird aus dieser Antwort ausgelassen; der Rest des Chats geht weiter.
- Die Liste gehört nur Ihnen. Was der Agent an ein Werkzeug übergibt, verlässt DataPlayer, einschließlich
  der aus Ihren Verbindungen gelesenen Daten.
- Eine Adresse auf diesem Rechner oder in seinem privaten Netz wird abgelehnt, es sei denn, die
  Installation erlaubt sie.

## Ein externer KI-Agent

Ein Agent außerhalb von DataPlayer — Claude Code, Cursor, Codex und andere — kann über die MCP-Adresse
von DataPlayer mit Ihren Verbindungen arbeiten.

1. **Einstellungen** im Benutzermenü, dann **MCP-Zugriff**.
2. **Neues Token**: ein Name, **Nur Lesen** oder **Voller Zugriff** und wann er abläuft. **Nur Lesen** liest
   Kataloge, Zeilen und Abfragen und lehnt jede Änderung ab; **Voller Zugriff** ändert Daten und führt
   Aktionen ohne Nachfrage aus.
3. Kopieren Sie den Token: Er wird nur einmal angezeigt. Das Fenster nennt außerdem die Zeile oder den
   Dateieintrag, der den gewählten Client einrichtet.

Der externe Agent hat dieselben Werkzeuge wie dieser, dieses Handbuch eingeschlossen, und liest nur
Verbindungen, deren Besitzer das Senden von Daten an Dritte erlaubt. **Token widerrufen** trennt ihn
beim nächsten Aufruf.

## Grenzen

- Eine Antwort macht höchstens 50 Werkzeugaufrufe; stellen Sie danach eine engere Frage.
- Ein Lesevorgang liefert höchstens 20 Zeilen auf einmal.
- Eine Nachricht trägt eine begrenzte Anzahl Dateien begrenzter Größe; das Eingabefeld sagt, welche
  Grenze erreicht wurde.
