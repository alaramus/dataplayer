"""Lo que escribe ClickHouse, en español (D226). Los términos siguen el glosario de las pantallas."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ClickHouse": "ClickHouse",
    'A ClickHouse server, over its HTTP interface. Browse databases, tables and views, read rows a page at a time with sorting and filtering done by the server, and run SQL.': 'Un servidor ClickHouse, a través de su interfaz HTTP. Explore bases de datos, tablas y vistas, lea filas página a página, ordenadas y filtradas por el servidor, y ejecute SQL.',
    "The HTTP interface: 8123, or 8443 with TLS": "La interfaz HTTP: 8123, o 8443 con TLS",
    "TLS": "TLS",
    "HTTPS, with the server's certificate verified": "HTTPS, con el certificado del servidor verificado",
    "That is not a ClickHouse connection string": "Esa no es una cadena de conexión de ClickHouse",
    "ClickHouse {version} is older than this source supports ({oldest})": "ClickHouse {version} es más antiguo de lo que admite esta fuente ({oldest})",
    # Relations and rows.
    'This ClickHouse source does not offer the "{representation}" content representation': "Esta fuente ClickHouse no ofrece la representación de contenido «{representation}»",
    "A filter value does not fit its column": "Un valor de filtro no encaja en su columna",
    "Changing the structure of a ClickHouse table is not supported yet": "Cambiar la estructura de una tabla de ClickHouse aún no es posible",
    "Editing ClickHouse rows is not supported yet": "Editar filas de ClickHouse aún no es posible",
    # The console.
    'ClickHouse keeps a change the moment it is made and cannot undo it, so a change cannot share a run with other statements; run it on its own': 'ClickHouse guarda un cambio en cuanto se hace y no puede deshacerlo, así que un cambio no puede compartir una ejecución con otras sentencias; ejecútelo por separado',
    'Detaching and attaching tables is not done from the query editor': 'Las tablas no se separan ni se adjuntan desde el editor de consultas',
    'Named collections are not changed from the query editor': 'Las colecciones con nombre no se cambian desde el editor de consultas',
    'SYSTEM commands manage the server and are not run from the query editor': 'Los comandos SYSTEM administran el servidor y no se ejecutan desde el editor de consultas',
    'The console shows a result itself; leave FORMAT out': 'La consola muestra el resultado por sí misma; quite FORMAT',
    'The query editor changes databases, tables, views and dictionaries; this is something else': 'El editor de consultas cambia bases de datos, tablas, vistas y diccionarios; esto es otra cosa',
}
