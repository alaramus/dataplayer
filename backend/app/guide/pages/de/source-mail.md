# E-Mail

Ihr Postfach in DataPlayer: Ordner, Briefe, Antworten und Anhänge, in einem
eigenen Tab statt in einem Katalog. Wie Verbindungen allgemein funktionieren,
steht auf der Seite [Verbindungen](connections.md).

## Was Sie sehen können

- Die Ordner des Postfachs, mit der Zahl der Briefe und der ungelesenen
- Die Briefe eines Ordners, die neuesten zuerst, fünfzig auf einmal
- Briefe, gefunden nach Wörtern in Absender, Betreff oder Text
- Einen Brief: von wem, an wen, sein Text und seine Anhänge
- Bilder aus dem Web in einem Brief, sobald Sie darum bitten
- Ein Hinweis, wenn neue Briefe im Posteingang ankommen

## Was Sie ändern können

- Neue Briefe, Antworten, Antworten an alle und Weiterleitungen mit ihren Dateien
- Briefe als gelesen oder ungelesen markiert
- Briefe in den Papierkorb verschoben und dort endgültig gelöscht
- Anhänge auf Ihrem Computer oder in Ihrem eigenen Ordner gespeichert
- Entwürfe speichern, später fertigstellen und senden
- Das Mikrofon neben dem Textfeld diktiert an der Schreibmarke
- Briefe in einen anderen Ordner verschieben
- Dateien aus Ihrem eigenen Ordner an einen Brief hängen

## Verbinden

Die Seite **Verbindung** fragt nach **E-Mail-Adresse** und **Ihr Name**,
**Anmeldename** (leer für die Adresse) und **Passwort** — bei Gmail, Yandex
oder Mail.ru ein App-Passwort —, nach **IMAP-Server**, **IMAP-Port** und
**IMAP-Sicherheit** (`tls` 993, `starttls` 143, `none` nur im eigenen Netz),
nach **SMTP-Server**, **SMTP-Port** und **SMTP-Sicherheit** (`tls` 465,
`starttls` 587), nach der **SMTP-Anmeldung** und ob eine **Kopie in „Gesendet“
abgelegt** werden soll — aus bei Gmail, das selbst eine ablegt.

**Prüfen** nennt den Schritt, der fehlschlug. Mit `starttls` wird ein Server,
der nicht verschlüsselt, abgelehnt statt das Passwort im Klartext zu erhalten.

## Der Tab „Mail“

Links die Ordner, in der Mitte die Briefe, rechts der geöffnete Brief. Ein
geöffneter Brief gilt als gelesen. Ein Brief als Webseite wird ohne Skripte
gezeigt, Bilder aus dem Web erst nach **Bilder anzeigen**. **Löschen**
verschiebt in den Papierkorb, im Papierkorb wird nach Rückfrage endgültig
gelöscht. Ein Anhang lässt sich **Herunterladen** oder **In meinem Ordner
speichern** — unter `Mail/<Adresse>/`, ohne Vorhandenes zu überschreiben und
innerhalb Ihres Speicherlimits. Anhänge eines neuen Briefs: bis 25 MB.

## Wer es öffnen kann

Nur Sie. Wer eine geteilte Verbindung erhält, sieht sie, kann das Postfach
aber nicht öffnen. Die Suche oben und der Agent lesen keine Post.

## Neues in diesem Postfach

Im Katalog gibt es zwei Karten: **E-Mail** für jeden Server und **Gmail**, die ihre Server selbst einträgt. Gmail braucht ein App-Passwort; Microsoft 365 und Outlook.com lehnen ein Passwort über IMAP ab und werden noch nicht angeboten.

Solange Sie angemeldet sind, wird der Posteingang etwa einmal pro Minute geprüft; neue Briefe melden sich mit **Öffnen**. **In einen Ordner verschieben** verschiebt den geöffneten Brief. **Aus meinem Ordner** hängt Dateien aus Ihrem Speicher an. **Entwurf speichern** legt den Brief in „Entwürfe“; dort setzt **Bearbeiten** ihn fort.

## Was E-Mail hier noch nicht kann

- Neue Briefe in anderen Ordnern als dem Posteingang melden
- Markierungen, Signaturen, einen Brief auf einen Ordner ziehen
- Gmail und Microsoft 365 ohne App-Passwort, Exchange ohne IMAP, SSH-Tunnel
