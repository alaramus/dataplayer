"""Ce que MongoDB écrit, en français (D226). Les termes suivent le glossaire des écrans."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "MongoDB": "MongoDB",
    "A MongoDB server. Browse databases, collections and views, and read documents a page at a time as rows, their fields found from the documents themselves, with sorting and filtering done by the server.": "Un serveur MongoDB. Parcourez les bases de données, les collections et les vues, et lisez les documents page par page sous forme de lignes, leurs champs déduits des documents eux-mêmes, avec tri et filtrage effectués par le serveur.",
    "Authentication database": "Base de données d'authentification",
    "Where the user is defined; admin unless it was made in another database": "Où l'utilisateur est défini ; admin, sauf s'il a été créé dans une autre base de données",
    "Encrypted, with the server's certificate verified": "Chiffré, avec vérification du certificat du serveur",
    "That is not a MongoDB connection string": "Ce n'est pas une chaîne de connexion MongoDB",
    "A mongodb+srv address is not supported; name one server with mongodb://": "Une adresse mongodb+srv n'est pas prise en charge ; indiquez un seul serveur avec mongodb://",
    "Name one server; a list of servers is not supported": "Indiquez un seul serveur ; une liste de serveurs n'est pas prise en charge",
    "MongoDB {version} is older than this source supports ({oldest})": "MongoDB {version} est plus ancien que ce que cette source prend en charge ({oldest})",
    "The server asks for a user and a password": "Le serveur demande un utilisateur et un mot de passe",
    "The connection settings are not usable": "Les paramètres de connexion ne sont pas utilisables",
    "The server refused the request": "Le serveur a refusé la requête",
    # Collections and documents.
    "View the definition": "Voir la définition",
    '"{node_id}" is not a collection: expected database.collection': "« {node_id} » n'est pas une collection : attendu base.collection",
    '"{name}" belongs to the server': "« {name} » appartient au serveur",
    "A collection has no columns of its own; every document has its own fields": "Une collection n'a pas de colonnes propres ; chaque document a ses propres champs",
    "Indexes are not changed here yet": "Les index ne sont pas encore modifiés ici",
    "MongoDB has no constraints but unique indexes": "MongoDB n'a pas d'autres contraintes que les index uniques",
    "Documents are not changed here yet": "Les documents ne sont pas encore modifiés ici",
    'This MongoDB source does not offer the "{representation}" content representation': "Cette source MongoDB ne propose pas la représentation de contenu « {representation} »",
}
