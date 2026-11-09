"""Lo que escribe Cassandra, en español (D226). Los términos siguen el glosario de las pantallas."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "Cassandra": "Cassandra",
    "Apache Cassandra": "Apache Cassandra",
    "ScyllaDB": "ScyllaDB",
    "Apache Cassandra or ScyllaDB, over CQL. Browse keyspaces, tables and materialized views, and read rows a page at a time with filtering done by the server.": "Apache Cassandra o ScyllaDB, mediante CQL. Explore keyspaces, tablas y vistas materializadas, y lea filas página a página con el filtrado hecho por el servidor.",
    "Keyspace": "Keyspace",
    "Where the catalog opens; every keyspace the role may see is in the catalog": "Dónde se abre el catálogo; en el catálogo está cada keyspace que el rol puede ver",
    "The native protocol's port, 9042 unless the server says otherwise": "El puerto del protocolo nativo, 9042 salvo que el servidor indique otro",
    "TLS, with the server's certificate verified": "TLS, con el certificado del servidor verificado",
    "Consistency": "Consistencia",
    "How many replicas answer a read and acknowledge a write": "Cuántas réplicas responden a una lectura y confirman una escritura",
    "That is not a Cassandra connection string": "Esa no es una cadena de conexión de Cassandra",
    "{product} {version} is older than this source supports ({oldest})": "{product} {version} es más antiguo de lo que admite este origen ({oldest})",
    "Keyspace does not exist": "El keyspace no existe",
    'Keyspace "{name}" does not exist': "El keyspace «{name}» no existe",
    "Not enough replicas are up for the consistency level asked": "No hay suficientes réplicas activas para el nivel de consistencia pedido",
    # Relations and rows.
    '"{node_id}" is not a relation: expected keyspace.table': "«{node_id}» no es una relación: se esperaba keyspace.tabla",
    '"{keyspace}" belongs to the server': "«{keyspace}» pertenece al servidor",
    "Cassandra has no unique keys and no foreign keys": "Cassandra no tiene claves únicas ni claves foráneas",
    "Partition key": "Clave de partición",
    "Clustering column, {order}": "Columna de clustering, {order}",
    "Static: one value for the whole partition": "Estática: un valor para toda la partición",
    'This Cassandra source does not offer the "{representation}" content representation': "Este origen de Cassandra no ofrece la representación de contenido «{representation}»",
    "This page is {rows} rows past the last one read; page forward from there": "Esta página está {rows} filas después de la última leída; avance página a página desde allí",
    "ScyllaDB's LIKE cannot look for % or _ in a value": "El LIKE de ScyllaDB no puede buscar % ni _ dentro de un valor",
    # The console and cqlsh.
    ":{name} is not a value of type {type}": ":{name} no es un valor de tipo {type}",
    "Cassandra keeps a change the moment it is made and cannot undo it, so a change cannot share a run with other statements; run it on its own, or put the changes in one BATCH": "Cassandra guarda un cambio en el momento en que se hace y no puede deshacerlo, así que un cambio no puede compartir una ejecución con otras sentencias; ejecútelo por separado o reúna los cambios en un BATCH",
    "No value was given for :{name}": "No se dio ningún valor para :{name}",
    "This connection has no keyspace called {name}": "Esta conexión no tiene ningún keyspace llamado {name}",
    "This is not a CQL statement this console runs": "Esta no es una sentencia CQL que ejecute esta consola",
    "cqlsh cannot read a user or a password that holds a line break": "cqlsh no puede leer un usuario o una contraseña con un salto de línea",
    "{command} is a cqlsh command, not CQL; run it in cqlsh in a terminal": "{command} es un comando de cqlsh, no CQL; ejecútelo en cqlsh en un terminal",
}
