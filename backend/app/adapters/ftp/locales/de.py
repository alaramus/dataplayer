"""What FTP writes, in German (D226).

The file side is the explorer's and words itself; these are the words of the
server, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "FTP": "FTP",
    "A server reached over FTP or FTPS. Browse its folders from where you choose and work with its files as with your own: tables, SQL over files, the editor, archives, search and copying between connections. Signs in with a password or anonymously.": "Ein über FTP oder FTPS erreichbarer Server. Durchsuchen Sie seine Ordner ab einer gewählten Stelle und arbeiten Sie mit seinen Dateien wie mit Ihren eigenen: Tabellen, SQL über Dateien, Editor, Archive, Suche und Kopieren zwischen Verbindungen. Anmeldung mit Passwort oder anonym.",
    "21, or 990 for implicit TLS": "21, oder 990 für implizites TLS",
    "Encryption": "Verschlüsselung",
    "TLS, explicit": "TLS, explizit",
    "TLS, implicit": "Keine Verschlüsselung",
    "No encryption": "TLS, implizit",
    "Off only for a server with a certificate of its own making": "Nur für einen Server mit selbst erstelltem Zertifikat ausschalten",
    "Where browsing starts; empty is the folder the server signs you into": "Wo das Durchsuchen beginnt; leer ist der Ordner, in den der Server Sie bei der Anmeldung bringt",
    "The host is a name or an address, without a scheme or a path": "Der Host ist ein Name oder eine Adresse, ohne Schema und Pfad",
    "The folder is one line": "Der Ordner steht in einer Zeile",
    "The user is one line": "Der Benutzer steht in einer Zeile",
    "A name with a line break in it cannot be sent to the server": "Ein Name mit Zeilenumbruch kann nicht an den Server gesendet werden",
    "Every connection to the server is busy": "Alle Verbindungen zum Server sind belegt",
    "That is not an FTP address": "Das ist keine FTP-Adresse",
    "The FTP connection has no host": "Die FTP-Verbindung hat keinen Host",
    "The TLS connection to the server failed": "Die TLS-Verbindung zum Server ist fehlgeschlagen",
    "The file is no longer on the server": "Die Datei ist nicht mehr auf dem Server",
    "The server closed the connection": "Der Server hat die Verbindung geschlossen",
    "The server did not accept this user and password": "Der Server hat diesen Benutzer und dieses Passwort nicht akzeptiert",
    "The server does not let anonymous users in": "Der Server lässt keine anonymen Benutzer zu",
    "The server does not offer TLS; choose no encryption to sign in without it": "Der Server bietet kein TLS an; wählen Sie „Keine Verschlüsselung“, um sich ohne anzumelden",
    "The server has too many connections open": "Der Server hat zu viele offene Verbindungen",
    "The server is busy; try again": "Der Server ist ausgelastet; versuchen Sie es erneut",
    "The server refused that": "Der Server hat das abgelehnt",
    "The server's certificate was not accepted": "Das Zertifikat des Servers wurde nicht akzeptiert",
    "The server's name could not be resolved": "Der Name des Servers konnte nicht aufgelöst werden",
    "There is no such folder on the server": "Diesen Ordner gibt es auf dem Server nicht",
}
