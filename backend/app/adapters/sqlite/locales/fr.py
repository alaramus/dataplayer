"""What SQLite writes, in French (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "SQLite": "SQLite",
    'A SQLite database file in your personal storage. Browse its tables and views, read rows a page at a time with sorting and filtering, and run SQL.': 'Un fichier de base de données SQLite dans votre stockage personnel. Parcourez ses tables et vues, lisez les lignes page par page avec tri et filtrage, et exécutez du SQL.',
    "Database file": "Fichier de base de données",
    "Path of the file inside your personal storage, such as data/shop.db": "Chemin du fichier dans votre stockage personnel, par exemple data/shop.db",
    "Create the file if it is missing": "Créer le fichier s'il n'existe pas",
    "Without this, a file that does not exist fails the connection check": "Sans cette option, un fichier inexistant échoue à la vérification de la connexion",
    "Name a file inside your personal storage": "Indiquez un fichier de votre stockage personnel",
    # Opening the file.
    "SQLite {version} is older than this source supports ({oldest})": "SQLite {version} est plus ancien que ce que cette source prend en charge ({oldest})",
    "The database file does not exist": "Le fichier de base de données n'existe pas",
    "The folder for the database file does not exist": "Le dossier du fichier de base de données n'existe pas",
    "The path names a folder, not a file": "Le chemin désigne un dossier, pas un fichier",
    "The file is not a SQLite database": "Le fichier n'est pas une base de données SQLite",
    "The database file is damaged": "Le fichier de base de données est endommagé",
    "The database file cannot be opened": "Impossible d'ouvrir le fichier de base de données",
    "The database file cannot be written": "Impossible d'écrire dans le fichier de base de données",
    "The database file is locked by another connection": "Le fichier de base de données est verrouillé par une autre connexion",
    "The database did not answer in time": "La base de données n'a pas répondu à temps",
    # The catalog and its relations.
    '"{name}" needs a module this server does not have': "« {name} » nécessite un module que ce serveur n'a pas",
    '"{node_id}" is not a relation: expected main.table': "« {node_id} » n'est pas une relation : attendu main.table",
    'This SQLite source does not offer the "{representation}" content representation': "Cette source SQLite ne propose pas la représentation de contenu « {representation} »",
    "Rows of a SQLite file are read only for now": "Les lignes d'un fichier SQLite sont pour l'instant en lecture seule",
    # The console.
    'A connection to this file opens no other file': "Une connexion à ce fichier n'ouvre aucun autre fichier",
    'Query plan': 'Plan de requête',
    'The query editor changes tables, views and indexes; this is something else': "L'éditeur de requêtes modifie les tables, les vues et les index ; ceci est autre chose",
}
