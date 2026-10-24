"""What SQLite writes, in Spanish (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "SQLite": "SQLite",
    'A SQLite database file in your personal storage. Browse its tables and views, read and edit rows a page at a time with sorting and filtering, and run SQL.': 'Un archivo de base de datos SQLite en tu almacenamiento personal. Explora sus tablas y vistas, lee y edita filas página a página con ordenación y filtrado, y ejecuta SQL.',
    "Database file": "Archivo de base de datos",
    "Path of the file inside your personal storage, such as data/shop.db": "Ruta del archivo dentro de tu almacenamiento personal, por ejemplo data/shop.db",
    "Create the file if it is missing": "Crear el archivo si no existe",
    "Without this, a file that does not exist fails the connection check": "Sin esto, un archivo que no existe no supera la comprobación de la conexión",
    "Name a file inside your personal storage": "Indica un archivo dentro de tu almacenamiento personal",
    # Opening the file.
    "SQLite {version} is older than this source supports ({oldest})": "SQLite {version} es más antiguo de lo que admite esta fuente ({oldest})",
    "The database file does not exist": "El archivo de base de datos no existe",
    "The folder for the database file does not exist": "La carpeta del archivo de base de datos no existe",
    "The path names a folder, not a file": "La ruta indica una carpeta, no un archivo",
    "The file is not a SQLite database": "El archivo no es una base de datos SQLite",
    "The database file is damaged": "El archivo de base de datos está dañado",
    "The database file cannot be opened": "No se puede abrir el archivo de base de datos",
    "The database file cannot be written": "No se puede escribir en el archivo de base de datos",
    "The database file is locked by another connection": "El archivo de base de datos está bloqueado por otra conexión",
    "The database did not answer in time": "La base de datos no respondió a tiempo",
    # The catalog and its relations.
    '"{name}" needs a module this server does not have': "«{name}» necesita un módulo que este servidor no tiene",
    '"{node_id}" is not a relation: expected main.table': "«{node_id}» no es una relación: se esperaba main.tabla",
    'This SQLite source does not offer the "{representation}" content representation': "Esta fuente SQLite no ofrece la representación de contenido «{representation}»",
    # The console.
    'A connection to this file opens no other file': 'Una conexión a este archivo no abre ningún otro archivo',
    'Query plan': 'Plan de consulta',
    'The query editor changes tables, views and indexes; this is something else': 'El editor de consultas modifica tablas, vistas e índices; esto es otra cosa',
    # Changing rows.
    '"{name}" belongs to SQLite': '«{name}» pertenece a SQLite',
    'Rows of a virtual table are not changed here': 'Las filas de una tabla virtual no se cambian aquí',
    'The rows of this table cannot be told apart': 'Las filas de esta tabla no se pueden distinguir',
    'The value is not of the type its column holds': 'El valor no es del tipo que guarda la columna',
}
