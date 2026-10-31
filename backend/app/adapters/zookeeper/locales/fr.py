"""Ce qu'écrit ZooKeeper, en français (D226)."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ZooKeeper": "ZooKeeper",
    "A ZooKeeper server. Walk its znode tree, read a znode's data as text or as JSON with its stat and ACL, edit the data against the version read, and page through a znode's children as rows.": "Un serveur ZooKeeper. Parcourir son arbre de znodes, lire les données d'un znode en texte ou en JSON avec son stat et son ACL, modifier les données par rapport à la version lue et parcourir page par page les enfants d'un znode sous forme de lignes.",
    "Anonymous": "Anonyme",
    "Digest": "Digest",
    "Root path": "Chemin racine",
    "Everything is read under this path, as if it were the top; empty for the whole tree": "Tout est lu sous ce chemin, comme s'il était le sommet ; vide pour l'arbre entier",
    "A root path starts with / and does not end with one": "Un chemin racine commence par / et ne se termine pas par /",
    "A root path has no empty, . or .. parts": "Un chemin racine n'a pas de partie vide, ni . ni ..",
    "A ZooKeeper connect string carries no user; choose Digest instead": "Une chaîne de connexion ZooKeeper ne contient pas d'utilisateur ; choisissez plutôt Digest",
    "Could not reach the ZooKeeper server": "Impossible de joindre le serveur ZooKeeper",
    "The root path does not exist on this server": "Le chemin racine n'existe pas sur ce serveur",
    "The ZooKeeper server could not do that": "Le serveur ZooKeeper n'a pas pu le faire",
    "The ZooKeeper server refused that": "Le serveur ZooKeeper l'a refusé",
    "This connection may not do that to this znode": "Cette connexion n'a pas le droit de faire cela à ce znode",
    "A znode with that name already exists": "Un znode portant ce nom existe déjà",
    "The znode has children": "Le znode a des enfants",
    "The server refused that ACL": "Le serveur a refusé cette ACL",
    # Znodes and their data.
    '"{node_id}" is not a znode of this source': "« {node_id} » n'est pas un znode de cette source",
    "A znode is opened as text or as a JSON tree": "Un znode s'ouvre en texte ou en arbre JSON",
    "View the data as JSON": "Afficher les données en JSON",
    "Edit the data": "Modifier les données",
    "View the children": "Afficher les enfants",
    "The data is not JSON": "Les données ne sont pas du JSON",
    "The data is not UTF-8 text, so it is shown as hex": "Les données ne sont pas du texte UTF-8 : elles sont affichées en hexadécimal",
    "The data is not UTF-8 text, so it is shown as hex and not edited here": "Les données ne sont pas du texte UTF-8 : elles sont affichées en hexadécimal et ne sont pas modifiées ici",
}
