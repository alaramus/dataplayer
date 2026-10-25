"""Ce que ClickHouse écrit, en français (D226). Les termes suivent le glossaire des écrans."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ClickHouse": "ClickHouse",
    'A ClickHouse server, over its HTTP interface. Browse databases, tables and views, read rows a page at a time with sorting and filtering done by the server, and run SQL.': 'Un serveur ClickHouse, par son interface HTTP. Parcourez les bases de données, les tables et les vues, lisez les lignes page par page, triées et filtrées par le serveur, et exécutez du SQL.',
    "The HTTP interface: 8123, or 8443 with TLS": "L’interface HTTP : 8123, ou 8443 avec TLS",
    "TLS": "TLS",
    "HTTPS, with the server's certificate verified": "HTTPS, avec vérification du certificat du serveur",
    "That is not a ClickHouse connection string": "Ce n’est pas une chaîne de connexion ClickHouse",
    "ClickHouse {version} is older than this source supports ({oldest})": "ClickHouse {version} est plus ancien que ce que cette source prend en charge ({oldest})",
    # Relations and rows.
    'This ClickHouse source does not offer the "{representation}" content representation': "Cette source ClickHouse ne propose pas la représentation de contenu « {representation} »",
    "A filter value does not fit its column": "Une valeur de filtre ne convient pas à sa colonne",
    "Changing the structure of a ClickHouse table is not supported yet": "La modification de la structure d’une table ClickHouse n’est pas encore prise en charge",
    "Editing ClickHouse rows is not supported yet": "La modification des lignes ClickHouse n’est pas encore prise en charge",
    # The console.
    'ClickHouse keeps a change the moment it is made and cannot undo it, so a change cannot share a run with other statements; run it on its own': 'ClickHouse conserve une modification dès qu’elle est faite et ne peut pas l’annuler, une modification ne peut donc pas partager une exécution avec d’autres instructions ; exécutez-la seule',
    'Detaching and attaching tables is not done from the query editor': 'Les tables ne sont pas détachées ni attachées depuis l’éditeur de requêtes',
    'Named collections are not changed from the query editor': 'Les collections nommées ne sont pas modifiées depuis l’éditeur de requêtes',
    'SYSTEM commands manage the server and are not run from the query editor': 'Les commandes SYSTEM administrent le serveur et ne sont pas exécutées depuis l’éditeur de requêtes',
    'The console shows a result itself; leave FORMAT out': 'La console affiche elle-même le résultat ; retirez FORMAT',
    'The query editor changes databases, tables, views and dictionaries; this is something else': 'L’éditeur de requêtes modifie les bases de données, les tables, les vues et les dictionnaires ; ceci est autre chose',
}
