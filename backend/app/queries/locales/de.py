"""Was das Ausführen von Abfragen sagt, auf Deutsch (D226). Die Begriffe folgen dem Glossar der Oberfläche."""

MESSAGES: dict[str, str] = {
    # Vor einem Lauf.
    "There is nothing to run": "Es gibt nichts auszuführen",
    "This is more than one statement; run it as a script to run them all": "Dies ist mehr als eine Anweisung; führen Sie sie als Skript aus, um alle auszuführen",
    "A script may hold at most {count} statements": "Ein Skript darf höchstens {count} Anweisungen enthalten",
    "Statement {at} is larger than one statement may be": "Anweisung {at} ist größer, als eine Anweisung sein darf",
    "Statement {at}: {refusal}": "Anweisung {at}: {refusal}",
    "Maintenance commands run outside a transaction; turn the manual transaction off to run this": "Wartungsbefehle laufen außerhalb einer Transaktion; schalten Sie die manuelle Transaktion aus, um diese auszuführen",
    "A maintenance command runs outside a transaction, so run it on its own": "Ein Wartungsbefehl läuft außerhalb einer Transaktion, führen Sie ihn daher einzeln aus",
    "Statement {at} is a {kind} statement, and this run is a read": "Anweisung {at} ist eine {kind}-Anweisung, und dieser Lauf ist ein Lesevorgang",
    "Statement {at} is a {kind} statement, and statements of that kind are not run here": "Anweisung {at} ist eine {kind}-Anweisung, und Anweisungen dieser Art werden hier nicht ausgeführt",
    "No value was given for {names}": "Für {names} wurde kein Wert angegeben",
    # Schreiben.
    "A write cannot run in read mode": "Ein Schreibvorgang kann nicht im Lesemodus ausgeführt werden",
    "The owner of this connection allows reading only": "Der Eigentümer dieser Verbindung erlaubt nur das Lesen",
    "A {kind} statement needs read access to this connection": "Eine {kind}-Anweisung benötigt Lesezugriff auf diese Verbindung",
    "A {kind} statement needs write access to this connection": "Eine {kind}-Anweisung benötigt Schreibzugriff auf diese Verbindung",
    "A {kind} statement needs structure access to this connection": "Eine {kind}-Anweisung benötigt Strukturzugriff auf diese Verbindung",
    "A {kind} statement needs own access to this connection": "Eine {kind}-Anweisung benötigt Eigentümerrechte an dieser Verbindung",
    "Confirm this write before running it": "Bestätigen Sie diesen Schreibvorgang, bevor Sie ihn ausführen",
    "This run asks for something that cannot be undone; confirm it first": "Dieser Lauf verlangt etwas, das nicht rückgängig gemacht werden kann; bestätigen Sie ihn zuerst",
    "You have read access to this connection": "Sie haben nur Lesezugriff auf diese Verbindung",
    # Ein Lauf.
    "This run could not be completed": "Dieser Lauf konnte nicht abgeschlossen werden",
    "There was no room to keep this result": "Es war kein Platz, um dieses Ergebnis zu behalten",
    # Transaktionen und Verlauf.
    "Committed {count} changing statement, {rows} rows": "{count} ändernde Anweisung festgeschrieben, {rows} Zeilen",
    "Committed {count} changing statements, {rows} rows": "{count} ändernde Anweisungen festgeschrieben, {rows} Zeilen",
    "Rolled back {count} changing statement": "{count} ändernde Anweisung zurückgerollt",
    "Rolled back {count} changing statements": "{count} ändernde Anweisungen zurückgerollt",
    "Document deleted": "Dokument gelöscht",
    "{count} runs deleted": "{count} Läufe gelöscht",
    # Suche.
    "Favorites": "Favoriten",
    "Untitled query": "Unbenannte Abfrage",
    "Only the newest {count} saved queries are searched by their title": "Nur die neuesten {count} gespeicherten Abfragen werden nach ihrem Titel durchsucht",
    "Stopped before every saved query was read": "Gestoppt, bevor jede gespeicherte Abfrage gelesen wurde",
    "Only the newest {count} saved queries are searched by their text": "Nur die neuesten {count} gespeicherten Abfragen werden nach ihrem Text durchsucht",
    "Saved query": "Gespeicherte Abfrage",
    "Saved query · {connection}": "Gespeicherte Abfrage · {connection}",
}
