"""Lo que escribe ZooKeeper, en español (D226)."""

MESSAGES: dict[str, str] = {
    # The source and its connection form.
    "ZooKeeper": "ZooKeeper",
    "A ZooKeeper server. Walk its znode tree, read a znode's data as text or as JSON with its stat and ACL, edit the data against the version read, and page through a znode's children as rows.": "Un servidor ZooKeeper. Recorrer su árbol de znodes, leer los datos de un znode como texto o como JSON con su stat y su ACL, editar los datos frente a la versión leída y recorrer por páginas los hijos de un znode como filas.",
    "Anonymous": "Anónimo",
    "Digest": "Digest",
    "Root path": "Ruta raíz",
    "Everything is read under this path, as if it were the top; empty for the whole tree": "Todo se lee bajo esta ruta, como si fuera la cima; vacía para el árbol entero",
    "A root path starts with / and does not end with one": "Una ruta raíz empieza por / y no termina en /",
    "A root path has no empty, . or .. parts": "Una ruta raíz no tiene partes vacías, ni . ni ..",
    "A ZooKeeper connect string carries no user; choose Digest instead": "Una cadena de conexión de ZooKeeper no lleva usuario; elija Digest",
    "Could not reach the ZooKeeper server": "No se pudo contactar con el servidor ZooKeeper",
    "The root path does not exist on this server": "La ruta raíz no existe en este servidor",
    "The ZooKeeper server could not do that": "El servidor ZooKeeper no pudo hacerlo",
    "The ZooKeeper server refused that": "El servidor ZooKeeper lo rechazó",
    "This connection may not do that to this znode": "Esta conexión no puede hacer eso con este znode",
    "A znode with that name already exists": "Ya existe un znode con ese nombre",
    "The znode has children": "El znode tiene hijos",
    "The server refused that ACL": "El servidor rechazó esa ACL",
    # Znodes and their data.
    '"{node_id}" is not a znode of this source': "«{node_id}» no es un znode de este origen",
    "A znode is opened as text or as a JSON tree": "Un znode se abre como texto o como árbol JSON",
    "View the data as JSON": "Ver los datos como JSON",
    "Edit the data": "Editar los datos",
    "View the children": "Ver los hijos",
    "The data is not JSON": "Los datos no son JSON",
    "The data is not UTF-8 text, so it is shown as hex": "Los datos no son texto UTF-8, así que se muestran en hexadecimal",
    "The data is not UTF-8 text, so it is shown as hex and not edited here": "Los datos no son texto UTF-8, así que se muestran en hexadecimal y no se editan aquí",
}
