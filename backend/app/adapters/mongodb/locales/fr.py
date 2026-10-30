"""Ce que MongoDB écrit, en français (D226). Les termes suivent le glossaire des écrans."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "MongoDB": "MongoDB",
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
    'This MongoDB source does not offer the "{representation}" content representation': "Cette source MongoDB ne propose pas la représentation de contenu « {representation} »",
    "A MongoDB server. Browse databases, collections and views, and read documents a page at a time as rows, their fields found from the documents themselves, with sorting and filtering done by the server, and work in mongosh in a terminal.": "Un serveur MongoDB. Parcourez les bases de données, les collections et les vues, lisez les documents page par page sous forme de lignes, leurs champs déduits des documents eux-mêmes, avec tri et filtrage effectués par le serveur, et travaillez dans mongosh dans un terminal.",
    "A console does not go through an SSH tunnel yet": "Une console ne passe pas encore par un tunnel SSH",
    "A time series takes new documents; the ones in it are not changed here": "Une série temporelle accepte de nouveaux documents ; ceux qu'elle contient ne sont pas modifiés ici",
    "A view's documents come from its pipeline and cannot be changed": "Les documents d'une vue proviennent de son pipeline et ne peuvent pas être modifiés",
    "Another document already has that value in a unique index": "Un autre document a déjà cette valeur dans un index unique",
    "The collection's validator refused the document": "Le validateur de la collection a refusé le document",
    "This document is larger than 256 KB; only its beginning is shown.": "Ce document dépasse 256 Ko ; seul son début est affiché.",
    "View as documents": "Voir sous forme de documents",
}
