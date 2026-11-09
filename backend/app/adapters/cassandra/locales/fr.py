"""Ce qu'écrit Cassandra, en français (D226). Les termes suivent le glossaire des écrans."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "Cassandra": "Cassandra",
    "Apache Cassandra": "Apache Cassandra",
    "ScyllaDB": "ScyllaDB",
    "Apache Cassandra or ScyllaDB, over CQL. Browse keyspaces, tables and materialized views, and read rows a page at a time with filtering done by the server.": "Apache Cassandra ou ScyllaDB, via CQL. Parcourir les keyspaces, les tables et les vues matérialisées, et lire les lignes page par page avec un filtrage effectué par le serveur.",
    "Keyspace": "Keyspace",
    "Where the catalog opens; every keyspace the role may see is in the catalog": "Où s'ouvre le catalogue ; chaque keyspace visible par le rôle figure dans le catalogue",
    "The native protocol's port, 9042 unless the server says otherwise": "Le port du protocole natif, 9042 sauf configuration contraire du serveur",
    "TLS, with the server's certificate verified": "TLS, avec vérification du certificat du serveur",
    "Consistency": "Cohérence",
    "How many replicas answer a read and acknowledge a write": "Combien de répliques répondent à une lecture et confirment une écriture",
    "That is not a Cassandra connection string": "Ce n'est pas une chaîne de connexion Cassandra",
    "{product} {version} is older than this source supports ({oldest})": "{product} {version} est plus ancien que ce que cette source prend en charge ({oldest})",
    "Keyspace does not exist": "Le keyspace n'existe pas",
    'Keyspace "{name}" does not exist': "Le keyspace « {name} » n'existe pas",
    "Not enough replicas are up for the consistency level asked": "Trop peu de répliques sont actives pour le niveau de cohérence demandé",
    # Relations and rows.
    '"{node_id}" is not a relation: expected keyspace.table': "« {node_id} » n'est pas une relation : keyspace.table attendu",
    '"{keyspace}" belongs to the server': "« {keyspace} » appartient au serveur",
    "Cassandra has no unique keys and no foreign keys": "Cassandra n'a ni clés uniques ni clés étrangères",
    "Partition key": "Clé de partition",
    "Clustering column, {order}": "Colonne de clustering, {order}",
    "Static: one value for the whole partition": "Statique : une valeur pour toute la partition",
    'This Cassandra source does not offer the "{representation}" content representation': "Cette source Cassandra ne propose pas la représentation de contenu « {representation} »",
    "This page is {rows} rows past the last one read; page forward from there": "Cette page se trouve {rows} lignes après la dernière lue ; avancez page par page à partir de celle-ci",
    "ScyllaDB's LIKE cannot look for % or _ in a value": "Le LIKE de ScyllaDB ne peut pas rechercher % ou _ dans une valeur",
    # The console and cqlsh.
    ":{name} is not a value of type {type}": ":{name} n'est pas une valeur de type {type}",
    "Cassandra keeps a change the moment it is made and cannot undo it, so a change cannot share a run with other statements; run it on its own, or put the changes in one BATCH": "Cassandra conserve une modification dès qu'elle est faite et ne peut pas l'annuler ; une modification ne peut donc pas partager une exécution avec d'autres instructions. Exécutez-la seule ou regroupez les modifications dans un BATCH",
    "No value was given for :{name}": "Aucune valeur n'a été donnée pour :{name}",
    "This connection has no keyspace called {name}": "Cette connexion n'a pas de keyspace nommé {name}",
    "This is not a CQL statement this console runs": "Ce n'est pas une instruction CQL que cette console exécute",
    "cqlsh cannot read a user or a password that holds a line break": "cqlsh ne peut pas lire un utilisateur ou un mot de passe contenant un saut de ligne",
    "{command} is a cqlsh command, not CQL; run it in cqlsh in a terminal": "{command} est une commande cqlsh, pas du CQL ; exécutez-la dans cqlsh dans un terminal",
}
