"""What DuckDB writes, in French (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    'DuckDB': 'DuckDB',
    'A DuckDB database file in your personal storage. Browse its schemas, tables and views, and read rows a page at a time with sorting and filtering.': 'Un fichier de base de données DuckDB dans votre stockage personnel. Parcourez ses schémas, tables et vues, et lisez les lignes page par page avec tri et filtrage.',
    'Path of the file inside your personal storage, such as data/shop.duckdb': 'Chemin du fichier dans votre stockage personnel, par exemple data/shop.duckdb',
    'The database file is in use by another program': 'Le fichier de base de données est utilisé par un autre programme',
    'The database reaches past your personal storage, which is refused': 'La base de données accède au-delà de votre stockage personnel, ce qui est refusé',
    'The file is not a DuckDB database this server can read': "Le fichier n'est pas une base de données DuckDB que ce serveur peut lire",
    'This DuckDB source does not offer the "{representation}" content representation': 'Cette source DuckDB ne propose pas la représentation de contenu « {representation} »',
    "A filter value does not fit its column's type": 'Une valeur de filtre ne correspond pas au type de sa colonne',
    'Rows of a DuckDB file are read only for now': "Les lignes d'un fichier DuckDB sont en lecture seule pour l'instant",
}
