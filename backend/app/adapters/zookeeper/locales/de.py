"""Was ZooKeeper schreibt, auf Deutsch (D226)."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ZooKeeper": "ZooKeeper",
    "A ZooKeeper server. Walk its znode tree, read a znode's data as text or as JSON with its stat and ACL, edit the data against the version read, and page through a znode's children as rows.": "Ein ZooKeeper-Server. Den Znode-Baum durchgehen, die Daten eines Znodes als Text oder JSON mit Stat und ACL lesen, die Daten gegen die gelesene Version bearbeiten und die Kinder eines Znodes seitenweise als Zeilen ansehen.",
    "Anonymous": "Anonym",
    "Digest": "Digest",
    "Root path": "Wurzelpfad",
    "Everything is read under this path, as if it were the top; empty for the whole tree": "Alles wird unter diesem Pfad gelesen, als wäre er die Spitze; leer für den ganzen Baum",
    "A root path starts with / and does not end with one": "Ein Wurzelpfad beginnt mit / und endet nicht damit",
    "A root path has no empty, . or .. parts": "Ein Wurzelpfad hat keine leeren Teile, kein . und kein ..",
    "A ZooKeeper connect string carries no user; choose Digest instead": "Eine ZooKeeper-Verbindungszeichenfolge enthält keinen Benutzer; wählen Sie stattdessen Digest",
    "Could not reach the ZooKeeper server": "Der ZooKeeper-Server ist nicht erreichbar",
    "The root path does not exist on this server": "Der Wurzelpfad existiert auf diesem Server nicht",
    "The ZooKeeper server could not do that": "Der ZooKeeper-Server konnte das nicht ausführen",
    "The ZooKeeper server refused that": "Der ZooKeeper-Server hat das abgelehnt",
    "This connection may not do that to this znode": "Diese Verbindung darf das mit diesem Znode nicht tun",
    "A znode with that name already exists": "Ein Znode mit diesem Namen existiert bereits",
    "The znode has children": "Der Znode hat Kinder",
    "The server refused that ACL": "Der Server hat diese ACL abgelehnt",
    # Znodes and their data.
    '"{node_id}" is not a znode of this source': "„{node_id}“ ist kein Znode dieser Quelle",
    "A znode is opened as text or as a JSON tree": "Ein Znode wird als Text oder als JSON-Baum geöffnet",
    "View the data as JSON": "Daten als JSON anzeigen",
    "Edit the data": "Daten bearbeiten",
    "View the children": "Kinder anzeigen",
    "The data is not JSON": "Die Daten sind kein JSON",
    "The data is not UTF-8 text, so it is shown as hex": "Die Daten sind kein UTF-8-Text und werden daher hexadezimal angezeigt",
    "The data is not UTF-8 text, so it is shown as hex and not edited here": "Die Daten sind kein UTF-8-Text, werden daher hexadezimal angezeigt und hier nicht bearbeitet",
}
