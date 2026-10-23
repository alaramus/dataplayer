"""What running queries says, in Spanish (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    # Before a run.
    "There is nothing to run": "No hay nada que ejecutar",
    "This is more than one statement; run it as a script to run them all": "Hay más de una instrucción; ejecútala como script para ejecutarlas todas",
    "A script may hold at most {count} statements": "Un script puede contener como máximo {count} instrucciones",
    "Statement {at} is larger than one statement may be": "La instrucción {at} supera el tamaño permitido para una instrucción",
    "Statement {at}: {refusal}": "Instrucción {at}: {refusal}",
    "Maintenance commands run outside a transaction; turn the manual transaction off to run this": "Los comandos de mantenimiento se ejecutan fuera de una transacción; desactiva la transacción manual para ejecutar este",
    "A maintenance command runs outside a transaction, so run it on its own": "Un comando de mantenimiento se ejecuta fuera de una transacción, así que ejecútalo por separado",
    "Statement {at} is a {kind} statement, and this run is a read": "La instrucción {at} es una instrucción {kind}, y esta ejecución es de solo lectura",
    "Statement {at} is a {kind} statement, and statements of that kind are not run here": "La instrucción {at} es una instrucción {kind}, y las instrucciones de ese tipo no se ejecutan aquí",
    "No value was given for {names}": "No se dio ningún valor para {names}",
    # Writing.
    "A write cannot run in read mode": "Una escritura no se puede ejecutar en modo de lectura",
    "The owner of this connection allows reading only": "El propietario de esta conexión solo permite lectura",
    "A {kind} statement needs read access to this connection": "Una instrucción {kind} necesita acceso de lectura a esta conexión",
    "A {kind} statement needs write access to this connection": "Una instrucción {kind} necesita acceso de escritura a esta conexión",
    "A {kind} statement needs structure access to this connection": "Una instrucción {kind} necesita acceso a la estructura de esta conexión",
    "A {kind} statement needs own access to this connection": "Una instrucción {kind} necesita permisos de propietario sobre esta conexión",
    "Confirm this write before running it": "Confirma esta escritura antes de ejecutarla",
    "This run asks for something that cannot be undone; confirm it first": "Esta ejecución solicita algo que no se puede deshacer; confírmala primero",
    "You have read access to this connection": "Tienes acceso de solo lectura a esta conexión",
    # A run.
    "This run could not be completed": "No se pudo completar esta ejecución",
    "There was no room to keep this result": "No había espacio para guardar este resultado",
    # Transactions and history.
    "Committed {count} changing statement, {rows} rows": "Se confirmó {count} instrucción que modifica datos, {rows} filas",
    "Committed {count} changing statements, {rows} rows": "Se confirmaron {count} instrucciones que modifican datos, {rows} filas",
    "Rolled back {count} changing statement": "Se revirtió {count} instrucción que modifica datos",
    "Rolled back {count} changing statements": "Se revirtieron {count} instrucciones que modifican datos",
    "Document deleted": "Documento eliminado",
    "{count} runs deleted": "Ejecuciones eliminadas: {count}",
    # Search.
    "Favorites": "Favoritos",
    "Untitled query": "Consulta sin título",
    "Only the newest {count} saved queries are searched by their title": "Solo se buscan por su título las {count} consultas guardadas más recientes",
    "Stopped before every saved query was read": "Se detuvo antes de leer todas las consultas guardadas",
    "Only the newest {count} saved queries are searched by their text": "Solo se buscan por su texto las {count} consultas guardadas más recientes",
    "Saved query": "Consulta guardada",
    "Saved query · {connection}": "Consulta guardada · {connection}",
}
