"""Was MongoDB schreibt, auf Deutsch (D226). Begriffe folgen dem Glossar der Bildschirme."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "MongoDB": "MongoDB",
    "Authentication database": "Authentifizierungsdatenbank",
    "Where the user is defined; admin unless it was made in another database": "Wo der Benutzer definiert ist; admin, sofern er nicht in einer anderen Datenbank angelegt wurde",
    "Encrypted, with the server's certificate verified": "Verschlüsselt, mit Prüfung des Serverzertifikats",
    "That is not a MongoDB connection string": "Das ist kein MongoDB-Verbindungsstring",
    "A mongodb+srv address is not supported; name one server with mongodb://": "Eine mongodb+srv-Adresse wird nicht unterstützt; geben Sie einen Server mit mongodb:// an",
    "Name one server; a list of servers is not supported": "Geben Sie einen Server an; eine Liste von Servern wird nicht unterstützt",
    "MongoDB {version} is older than this source supports ({oldest})": "MongoDB {version} ist älter, als diese Quelle unterstützt ({oldest})",
    "The server asks for a user and a password": "Der Server verlangt einen Benutzer und ein Passwort",
    "The connection settings are not usable": "Mit diesen Verbindungseinstellungen ist keine Verbindung möglich",
    "The server refused the request": "Der Server hat die Anfrage abgelehnt",
    # Collections and documents.
    "View the definition": "Definition anzeigen",
    '"{node_id}" is not a collection: expected database.collection': "„{node_id}“ ist keine Collection: erwartet Datenbank.Collection",
    '"{name}" belongs to the server': "„{name}“ gehört dem Server",
    "A collection has no columns of its own; every document has its own fields": "Eine Collection hat keine eigenen Spalten; jedes Dokument hat seine eigenen Felder",
    "Indexes are not changed here yet": "Indizes werden hier noch nicht geändert",
    "MongoDB has no constraints but unique indexes": "MongoDB hat außer eindeutigen Indizes keine Constraints",
    "Documents are not changed here yet": "Dokumente werden hier noch nicht geändert",
    'This MongoDB source does not offer the "{representation}" content representation': "Diese MongoDB-Quelle bietet die Inhaltsdarstellung „{representation}“ nicht an",
    "A MongoDB server. Browse databases, collections and views, and read documents a page at a time as rows, their fields found from the documents themselves, with sorting and filtering done by the server, and work in mongosh in a terminal.": "Ein MongoDB-Server. Datenbanken, Collections und Views durchsuchen, Dokumente seitenweise als Zeilen lesen, ihre Felder aus den Dokumenten selbst ermittelt, sortiert und gefiltert vom Server, und in mongosh in einem Terminal arbeiten.",
    "A console does not go through an SSH tunnel yet": "Eine Konsole läuft noch nicht durch einen SSH-Tunnel",
}
