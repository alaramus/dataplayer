"""Ce que ClickHouse écrit, en français (D226). Les termes suivent le glossaire des écrans."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ClickHouse": "ClickHouse",
    "A ClickHouse server, over its HTTP interface. Browse databases, tables and views, and read rows a page at a time with sorting and filtering done by the server.": "Un serveur ClickHouse, par son interface HTTP. Parcourez les bases de données, les tables et les vues, et lisez les lignes page par page, triées et filtrées par le serveur.",
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
}
