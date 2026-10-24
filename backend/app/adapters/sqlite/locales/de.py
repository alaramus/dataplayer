"""What SQLite writes, in German (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "SQLite": "SQLite",
    'A SQLite database file in your personal storage. Browse its tables and views, read and edit rows a page at a time with sorting and filtering, and run SQL.': 'Eine SQLite-Datenbankdatei in Ihrem persönlichen Speicher. Tabellen und Sichten durchsuchen, Zeilen seitenweise mit Sortierung und Filterung lesen und bearbeiten und SQL ausführen.',
    "Database file": "Datenbankdatei",
    "Path of the file inside your personal storage, such as data/shop.db": "Pfad der Datei in Ihrem persönlichen Speicher, etwa data/shop.db",
    "Create the file if it is missing": "Datei anlegen, wenn sie fehlt",
    "Without this, a file that does not exist fails the connection check": "Ohne diese Option besteht eine nicht vorhandene Datei die Verbindungsprüfung nicht",
    "Name a file inside your personal storage": "Geben Sie eine Datei in Ihrem persönlichen Speicher an",
    # Opening the file.
    "SQLite {version} is older than this source supports ({oldest})": "SQLite {version} ist älter, als diese Quelle unterstützt ({oldest})",
    "The database file does not exist": "Die Datenbankdatei existiert nicht",
    "The folder for the database file does not exist": "Der Ordner für die Datenbankdatei existiert nicht",
    "The path names a folder, not a file": "Der Pfad bezeichnet einen Ordner, keine Datei",
    "The file is not a SQLite database": "Die Datei ist keine SQLite-Datenbank",
    "The database file is damaged": "Die Datenbankdatei ist beschädigt",
    "The database file cannot be opened": "Die Datenbankdatei kann nicht geöffnet werden",
    "The database file cannot be written": "In die Datenbankdatei kann nicht geschrieben werden",
    "The database file is locked by another connection": "Die Datenbankdatei ist von einer anderen Verbindung gesperrt",
    "The database did not answer in time": "Die Datenbank hat nicht rechtzeitig geantwortet",
    # The catalog and its relations.
    '"{name}" needs a module this server does not have': "„{name}“ benötigt ein Modul, das dieser Server nicht hat",
    '"{node_id}" is not a relation: expected main.table': "„{node_id}“ ist keine Relation: erwartet wird main.Tabelle",
    'This SQLite source does not offer the "{representation}" content representation': "Diese SQLite-Quelle bietet die Inhaltsdarstellung „{representation}“ nicht an",
    # The console.
    'A connection to this file opens no other file': 'Eine Verbindung zu dieser Datei öffnet keine andere Datei',
    'Query plan': 'Abfrageplan',
    'The query editor changes tables, views and indexes; this is something else': 'Der Abfrageeditor ändert Tabellen, Sichten und Indizes; dies ist etwas anderes',
    # Changing rows.
    '"{name}" belongs to SQLite': '„{name}“ gehört zu SQLite',
    'Rows of a virtual table are not changed here': 'Zeilen einer virtuellen Tabelle werden hier nicht geändert',
    'The rows of this table cannot be told apart': 'Die Zeilen dieser Tabelle lassen sich nicht unterscheiden',
    'The value is not of the type its column holds': 'Der Wert hat nicht den Typ, den die Spalte enthält',
}
