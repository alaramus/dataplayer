"""Lo que escribe ClickHouse, en español (D226). Los términos siguen el glosario de las pantallas."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ClickHouse": "ClickHouse",
    "A ClickHouse server, over its HTTP interface. Browse databases, tables and views, and read rows a page at a time with sorting and filtering done by the server.": "Un servidor ClickHouse, a través de su interfaz HTTP. Explore bases de datos, tablas y vistas, y lea filas página a página, ordenadas y filtradas por el servidor.",
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
}
