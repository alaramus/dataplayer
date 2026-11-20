"""What DuckDB writes, in German (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    'DuckDB': 'DuckDB',
    'Path of the file inside your personal storage, such as data/shop.duckdb': 'Pfad der Datei in Ihrem persönlichen Speicher, etwa data/shop.duckdb',
    'The database file is in use by another program': 'Die Datenbankdatei wird von einem anderen Programm verwendet',
    'The database reaches past your personal storage, which is refused': 'Die Datenbank greift über Ihren persönlichen Speicher hinaus, das wird abgelehnt',
    'The file is not a DuckDB database this server can read': 'Die Datei ist keine DuckDB-Datenbank, die dieser Server lesen kann',
    'This DuckDB source does not offer the "{representation}" content representation': 'Diese DuckDB-Quelle bietet die Inhaltsdarstellung „{representation}“ nicht an',
    "A filter value does not fit its column's type": 'Ein Filterwert passt nicht zum Typ seiner Spalte',
    'Rows of a DuckDB file are read only for now': 'Zeilen einer DuckDB-Datei sind vorerst schreibgeschützt',
    'A DuckDB database file in your personal storage. Browse its schemas, tables and views, read rows a page at a time with sorting and filtering, and run SQL over the file and the other files of your storage.': 'Eine DuckDB-Datenbankdatei in Ihrem persönlichen Speicher. Durchsuchen Sie ihre Schemas, Tabellen und Sichten, lesen Sie Zeilen seitenweise mit Sortierung und Filterung und führen Sie SQL über die Datei und die anderen Dateien Ihres Speichers aus.',
    'A connection to this file opens no other database': 'Eine Verbindung zu dieser Datei öffnet keine andere Datenbank',
    'DuckDB has no savepoints, so a change cannot be tried out inside a held transaction; run it in auto-commit, where it is tried out first': 'DuckDB hat keine Sicherungspunkte, daher lässt sich eine Änderung in einer gehaltenen Transaktion nicht erproben; führen Sie sie im Auto-Commit aus, wo sie zuerst erprobt wird',
    'Extensions are not installed or loaded here': 'Erweiterungen werden hier weder installiert noch geladen',
    "Files are not written or loaded from the query editor; load one with INSERT … SELECT * FROM '~/file.csv'": "Dateien werden im Abfrageeditor weder geschrieben noch geladen; laden Sie eine mit INSERT … SELECT * FROM '~/file.csv'",
    'Secrets are of no use here: this engine reaches no network': 'Geheimnisse nützen hier nichts: Diese Engine erreicht kein Netz',
    'Statements are not prepared here; write parameters as $name': 'Anweisungen werden hier nicht vorbereitet; schreiben Sie Parameter als $name',
    "The engine's settings are fixed; the schema is chosen above the editor": 'Die Einstellungen der Engine sind fest; das Schema wird über dem Editor gewählt',
    'The query editor changes tables, views, indexes, schemas, sequences, types and macros; this is something else': 'Der Abfrageeditor ändert Tabellen, Sichten, Indizes, Schemas, Sequenzen, Typen und Makros; dies ist etwas anderes',
    'The statement could not be read': 'Die Anweisung konnte nicht gelesen werden',
    'This result holds a moment with a time zone; select it with SELECT to see it': 'Dieses Ergebnis enthält einen Zeitpunkt mit Zeitzone; wählen Sie ihn mit SELECT aus, um ihn zu sehen',
}
