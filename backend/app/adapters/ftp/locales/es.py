"""What FTP writes, in Spanish (D226).

The file side is the explorer's and words itself; these are the words of the
server, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "FTP": "FTP",
    "A server reached over FTP or FTPS. Browse its folders from where you choose and work with its files as with your own: tables, SQL over files, the editor, archives, search and copying between connections. Signs in with a password or anonymously.": "Un servidor al que se llega por FTP o FTPS. Explore sus carpetas desde donde elija y trabaje con sus archivos como con los suyos: tablas, SQL sobre archivos, el editor, archivos comprimidos, búsqueda y copia entre conexiones. Inicia sesión con contraseña o de forma anónima.",
    "21, or 990 for implicit TLS": "21, o 990 para TLS implícito",
    "Encryption": "Cifrado",
    "TLS, explicit": "TLS, explícito",
    "TLS, implicit": "Sin cifrado",
    "No encryption": "TLS, implícito",
    "Off only for a server with a certificate of its own making": "Desactívelo solo para un servidor con un certificado hecho por usted",
    "Where browsing starts; empty is the folder the server signs you into": "Dónde empieza la navegación; vacío es la carpeta en la que el servidor le deja al entrar",
    "The host is a name or an address, without a scheme or a path": "El host es un nombre o una dirección, sin esquema ni ruta",
    "The folder is one line": "La carpeta va en una sola línea",
    "The user is one line": "El usuario va en una sola línea",
    "A name with a line break in it cannot be sent to the server": "Un nombre con un salto de línea no se puede enviar al servidor",
    "Every connection to the server is busy": "Todas las conexiones con el servidor están ocupadas",
    "That is not an FTP address": "Esa no es una dirección FTP",
    "The FTP connection has no host": "La conexión FTP no tiene host",
    "The TLS connection to the server failed": "La conexión TLS con el servidor falló",
    "The file is no longer on the server": "El archivo ya no está en el servidor",
    "The server closed the connection": "El servidor cerró la conexión",
    "The server did not accept this user and password": "El servidor no aceptó este usuario y contraseña",
    "The server does not let anonymous users in": "El servidor no admite usuarios anónimos",
    "The server does not offer TLS; choose no encryption to sign in without it": "El servidor no ofrece TLS; elija «Sin cifrado» para entrar sin él",
    "The server has too many connections open": "El servidor tiene demasiadas conexiones abiertas",
    "The server is busy; try again": "El servidor está ocupado; inténtelo de nuevo",
    "The server refused that": "El servidor lo rechazó",
    "The server's certificate was not accepted": "No se aceptó el certificado del servidor",
    "The server's name could not be resolved": "No se pudo resolver el nombre del servidor",
    "There is no such folder on the server": "No existe esa carpeta en el servidor",
}
