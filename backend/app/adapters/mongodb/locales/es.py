"""Lo que escribe MongoDB, en español (D226). Los términos siguen el glosario de las pantallas."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "MongoDB": "MongoDB",
    "Authentication database": "Base de datos de autenticación",
    "Where the user is defined; admin unless it was made in another database": "Dónde está definido el usuario; admin, salvo que se creara en otra base de datos",
    "Encrypted, with the server's certificate verified": "Cifrado, con verificación del certificado del servidor",
    "That is not a MongoDB connection string": "Eso no es una cadena de conexión de MongoDB",
    "A mongodb+srv address is not supported; name one server with mongodb://": "No se admite una dirección mongodb+srv; indique un solo servidor con mongodb://",
    "Name one server; a list of servers is not supported": "Indique un solo servidor; no se admite una lista de servidores",
    "MongoDB {version} is older than this source supports ({oldest})": "MongoDB {version} es más antiguo de lo que admite este origen ({oldest})",
    "The server asks for a user and a password": "El servidor pide un usuario y una contraseña",
    "The connection settings are not usable": "No se puede conectar con esta configuración",
    "The server refused the request": "El servidor rechazó la solicitud",
    # Collections and documents.
    "View the definition": "Ver la definición",
    '"{node_id}" is not a collection: expected database.collection': "«{node_id}» no es una colección: se esperaba base_de_datos.colección",
    '"{name}" belongs to the server': "«{name}» pertenece al servidor",
    "A collection has no columns of its own; every document has its own fields": "Una colección no tiene columnas propias; cada documento tiene sus propios campos",
    "Indexes are not changed here yet": "Aquí todavía no se modifican los índices",
    "MongoDB has no constraints but unique indexes": "MongoDB no tiene más restricciones que los índices únicos",
    'This MongoDB source does not offer the "{representation}" content representation': "Este origen MongoDB no ofrece la representación de contenido «{representation}»",
    "A MongoDB server. Browse databases, collections and views, and read documents a page at a time as rows, their fields found from the documents themselves, with sorting and filtering done by the server, and work in mongosh in a terminal.": "Un servidor MongoDB. Explore bases de datos, colecciones y vistas, lea documentos página a página como filas, con sus campos deducidos de los propios documentos y la ordenación y el filtrado hechos por el servidor, y trabaje en mongosh en un terminal.",
    "A console does not go through an SSH tunnel yet": "Una consola todavía no pasa por un túnel SSH",
    "A time series takes new documents; the ones in it are not changed here": "Una serie temporal admite documentos nuevos; los que ya contiene no se modifican aquí",
    "A view's documents come from its pipeline and cannot be changed": "Los documentos de una vista proceden de su canalización y no se pueden modificar",
    "Another document already has that value in a unique index": "Otro documento ya tiene ese valor en un índice único",
    "The collection's validator refused the document": "El validador de la colección rechazó el documento",
    "This document is larger than 256 KB; only its beginning is shown.": "Este documento supera los 256 KB; solo se muestra su comienzo.",
    "View as documents": "Ver como documentos",
}
