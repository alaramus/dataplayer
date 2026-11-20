"""What DuckDB writes, in German (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    'DuckDB': 'DuckDB',
    'A DuckDB database file in your personal storage. Browse its schemas, tables and views, and read rows a page at a time with sorting and filtering.': 'Eine DuckDB-Datenbankdatei in Ihrem persönlichen Speicher. Durchsuchen Sie ihre Schemas, Tabellen und Sichten und lesen Sie Zeilen seitenweise mit Sortierung und Filterung.',
    'Path of the file inside your personal storage, such as data/shop.duckdb': 'Pfad der Datei in Ihrem persönlichen Speicher, etwa data/shop.duckdb',
    'The database file is in use by another program': 'Die Datenbankdatei wird von einem anderen Programm verwendet',
    'The database reaches past your personal storage, which is refused': 'Die Datenbank greift über Ihren persönlichen Speicher hinaus, das wird abgelehnt',
    'The file is not a DuckDB database this server can read': 'Die Datei ist keine DuckDB-Datenbank, die dieser Server lesen kann',
    'This DuckDB source does not offer the "{representation}" content representation': 'Diese DuckDB-Quelle bietet die Inhaltsdarstellung „{representation}“ nicht an',
    "A filter value does not fit its column's type": 'Ein Filterwert passt nicht zum Typ seiner Spalte',
    'Rows of a DuckDB file are read only for now': 'Zeilen einer DuckDB-Datei sind vorerst schreibgeschützt',
}
