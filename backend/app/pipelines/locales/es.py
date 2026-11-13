"""What a pipeline and its runs say, in Spanish (D226). Terms follow the screens' glossary."""

MESSAGES: dict[str, str] = {
    # Carrying a run out.
    "running its links": "ejecutando sus enlaces",
    "{name} is gone, or no longer shared with you": "{name} ya no existe o ya no se comparte contigo",
    "{name} is switched off": "{name} está desactivada",
    "{name} can no longer be opened": "{name} ya no se puede abrir",
    "You no longer have read access to {name}": "Ya no tienes acceso de lectura a {name}",
    "You no longer have write access to {name}": "Ya no tienes acceso de escritura a {name}",
    "You no longer have structure access to {name}": "Ya no tienes acceso a la estructura de {name}",
    "You no longer have own access to {name}": "Ya no tienes permisos de propietario sobre {name}",
    "The link could not run": "No se pudo ejecutar el enlace",
    "{link} made nothing in this run": "«{link}» no creó nada en esta ejecución",
    "Its owner is no longer here": "Su propietario ya no está",
    "{kind} is not possible between these connections": "«{kind}» no es posible entre estas conexiones",
    "{kind} cannot run": "«{kind}» no se puede ejecutar",
    "The link it reads": "El enlace que lee",
    "This run could not be read; nothing ran": "No se pudo leer esta ejecución; no se ejecutó nada",
    # A run's sentence.
    "{said}; {count} not run": "{said}; no ejecutados: {count}",
    "{done} of {count} links ran": "Se ejecutaron {done} de {count} enlaces",
    "Its one link ran": "Se ejecutó su único enlace",
    "All {count} links ran": "Se ejecutaron los {count} enlaces",
    "Stopped at {at} of {count}, {title}: {reason}": "Se detuvo en {at} de {count}, «{title}»: {reason}",
    "Stopped at {at} of {count}, {title}": "Se detuvo en {at} de {count}, «{title}»",
    "Stopped on request at {at} of {count}, {title}": "Se detuvo a petición en {at} de {count}, «{title}»",
    "Stopped on request before its first link": "Se detuvo a petición antes de su primer enlace",
    "Stopped on request after {done} of {count}": "Se detuvo a petición después de {done} de {count}",
    # Starting a run.
    "{number} · {title} needs its table named and its columns chosen": "{number} · «{title}» necesita que se indique la tabla y se elijan las columnas",
    "{number} · {title} needs its columns paired": "{number} · «{title}» necesita que se emparejen sus columnas",
    "a result": "un resultado",
    "{connection} (top)": "{connection} (nivel superior)",
    "Nothing ran: {needs}": "No se ejecutó nada: {needs}",
    # The canvas.
    "This connection is gone, or no longer shared with you": "Esta conexión ya no existe o ya no se comparte contigo",
    "This connection is switched off": "Esta conexión está desactivada",
    "This connection cannot be read": "No se puede leer esta conexión",
    "{names} and {last}": "{names} y {last}",
    "{names} write into each other, so the arrows give no first link: this one goes first because its card is furthest left": "{names} escriben entre sí, así que las flechas no determinan el primer enlace: este va primero porque su tarjeta está más a la izquierda",
    "{names} write into each other, so the arrows give no first link: this one goes first because its card is highest": "{names} escriben entre sí, así que las flechas no determinan el primer enlace: este va primero porque su tarjeta está más arriba",
    "{names} write into each other, so the arrows give no first link: this one goes first because it starts from the highest row": "{names} escriben entre sí, así que las flechas no determinan el primer enlace: este va primero porque empieza desde la fila más alta",
    "{names} write into each other, so the arrows give no first link: this one goes first because it was drawn first": "{names} escriben entre sí, así que las flechas no determinan el primer enlace: este va primero porque se dibujó primero",
    "{names} write into each other, so the arrows give no first link: this one goes first because the others wait for links outside them as well": "{names} escriben entre sí, así que las flechas no determinan el primer enlace: este va primero porque los demás también esperan enlaces fuera de ellos",
    "{name} was removed": "Se eliminó {name}",
    # Search.
    "Pipelines": "Flujos",
    "Pipeline": "Flujo",
    # A link keeping the latest per key (D314).
    "{number} · {title} needs its key and values chosen": "{number} · «{title}» necesita que se elijan su clave y sus valores",
    # A pipeline following its topics (D315).
    "Followed; {count} messages carried": "Seguimiento; mensajes llevados: {count}",
    "Only a link reading a topic follows it": "Solo un enlace que lee un topic puede seguirlo",
    "This following could not be read": "No se pudo leer este seguimiento",
    "following its topics": "siguiendo sus topics",
    # A pipeline switched on with one button (D362, D363).
    "Runs continuously; not run": "Se ejecuta de forma continua; no se ejecutó",
    "Not switched on: {needs}": "No se encendió: {needs}",
    "Same connection": "La misma conexión",
    "Nothing can go from here into this connection": "Nada puede ir desde aquí a esta conexión",
    "Already linked": "Ya enlazado",
    "Nothing can go here": "Nada puede ir aquí",
}
