# Einstellungen und Konto

**Einstellungen** im Benutzermenü oben rechts enthält, was Ihnen gehört und nicht einer einzelnen
Verbindung. **Abmelden** steht im selben Menü.

## Allgemein

- **Sprache**: die Sprache der gesamten Oberfläche. Sie wird mit Ihrem Konto gespeichert, folgt Ihnen also
  in jedem Browser. Solange keine gewählt ist, gilt die Sprache des Browsers.
- **Erscheinungsbild**: ein helles oder dunkles Design oder **System**, das dem Betriebssystem folgt. Mit dem Konto
  gespeichert.
- **Lesestimme**: die Stimme, die Nachrichten vorliest. Stimmen gehören dem Browser, deshalb wird diese
  Einstellung in diesem Browser gespeichert.
- **Persönlicher Speicher**: wie viel Ihrer eigenen Dateien auf diesem Server Sie nutzen, im Vergleich zu dem
  Limit, das ein Administrator gesetzt hat.

## Verbindungen

**Wie oft Verbindungen geprüft werden**: Jede Verbindung wird nach diesem Zeitplan geprüft, solange ein
Arbeitsbereich geöffnet ist, und der Punkt daneben in der Liste zeigt die letzte Antwort. **Nie** prüft nur,
wenn Sie darum bitten. Ein langsamer oder entfernter Server sollte seltener gefragt werden.

## SSH-Schlüssel

Die Schlüssel, mit denen sich Ihre SSH-Verbindungen anmelden. Mehr dazu steht auf der Seite [SSH](source-ssh.md).

- **Neuer Schlüssel** erzeugt einen auf diesem Server, wo er bleibt. **Den öffentlichen Schlüssel kopieren** und tragen Sie ihn in
  `authorized_keys` auf den Servern ein, die er öffnen soll.
- **Importieren** übernimmt einen Schlüssel, den Sie schon haben.
- Ein Schlüssel kann seine Passphrase behalten, keine haben oder danach fragen. Einer, der fragt, ist
  **Gesperrt**, bis Sie ihn für 15 Minuten, 1 Stunde oder 8 Stunden mit **Entsperren** entsperren; **Jetzt sperren**
  sperrt ihn wieder.
- Ein Schlüssel, den eine Verbindung benutzt, kann nicht gelöscht werden, solange ihre Verbindungen keinen
  anderen verwenden.

## Touren

Die Willkommenstour und kurze Touren durch jeden Teil von DataPlayer — eine Tabelle auf andere Weise lesen,
eine Pipeline, Dashboards, der Agent. **Starten** startet eine, **Noch einmal** wiederholt eine bereits gemachte. Eine
Tour legt für sich eine Übungsdatenbank an und entfernt sie am Ende wieder.

## MCP-Zugriff

Token, mit denen ein KI-Agent außerhalb von DataPlayer, etwa Claude Code, Cursor oder Codex, mit Ihren
Verbindungen arbeitet. Wie man einen erstellt, steht auf der Seite [Der KI-Agent](assistant.md).

## Verwaltung

Ein Administrator hat außerdem **Verwaltung** im Benutzermenü, mit **Benutzer**:

- **Neuer Benutzer** legt ein Konto an. Es wartet auf ein Passwort: **Link zum Festlegen des Passworts** liefert einen Link,
  den Sie der Person senden; er funktioniert einmal und für begrenzte Zeit. Derselbe Link setzt ein vergessenes
  Passwort zurück.
- **Dieses Konto bearbeiten** ändert den Namen, ob die Person **Kann sich anmelden** darf, ob sie **Administrator** ist, und
  ihr **Speicherlimit**.
- **Dieses Konto und alles, was es besitzt, löschen** entfernt die Person mit ihren Verbindungen und Dateien.

Ein Administrator verwaltet Konten, nicht die Daten anderer: Er sieht die Verbindungen anderer Personen nicht.
