"""Lo que escribe SSH, en español (D226). Los términos siguen el glosario de las pantallas.

El lado de los archivos es del explorador y tiene sus propias palabras; estas
son las palabras del servidor, su clave y el inicio de sesión.
"""

MESSAGES: dict[str, str] = {
    # La fuente y su formulario de conexión.
    "SSH": "SSH",
    "A server reached over SSH. Browse its folders from where you choose and work with its files as with your own: tables, SQL over files, the editor, archives, search, and a terminal. Signs in with a password or one of your SSH keys, and only to the server whose key you confirmed.": "Un servidor al que se accede por SSH. Explora sus carpetas desde donde elijas y trabaja con sus archivos como con los tuyos: tablas, SQL sobre archivos, el editor, archivos comprimidos, búsqueda y una terminal. Inicia sesión con una contraseña o con una de tus claves SSH, y solo en el servidor cuya clave hayas confirmado.",
    "Authentication": "Autenticación",
    "Host": "Host",
    "Port": "Puerto",
    "User": "Usuario",
    "Folder": "Carpeta",
    "Where browsing starts; empty is the user's home folder": "Dónde empieza la exploración; si está vacío, la carpeta personal del usuario",
    "Server key": "Clave del servidor",
    "What this server proves itself with; fetch it and compare": "Con qué demuestra este servidor que es él; obtén la clave y compárala",
    "Key": "Clave",
    "One of your SSH keys; its public half goes to the server": "Una de tus claves SSH; su parte pública se envía al servidor",
    "Password": "Contraseña",
    # Direcciones.
    "The SSH connection has no host": "La conexión SSH no indica ningún host",
    "That is not an SSH URL": "Eso no es una URL de SSH",
    "Enter the host first": "Indica primero el host",
    # Claves.
    "This is not a server key this application can read": "Esta no es una clave de servidor que esta aplicación pueda leer",
    "That passphrase does not open this key": "Esa frase de contraseña no abre esta clave",
    "This key is protected by a passphrase; enter it": "Esta clave está protegida por una frase de contraseña; introdúcela",
    "This is not a private key this application can read": "Esta no es una clave privada que esta aplicación pueda leer",
    # Conexión.
    "Connection successful": "Conexión establecida",
    "This connection signs in with a key, and none is at hand": "Esta conexión inicia sesión con una clave, y no hay ninguna disponible",
    "Fetch the server's key and confirm it before connecting": "Obtén la clave del servidor y confírmala antes de conectar",
    "The server key of this connection cannot be read": "No se puede leer la clave del servidor de esta conexión",
    "The SSH key could not be opened with its passphrase": "No se pudo abrir la clave SSH con su frase de contraseña",
    "The server did not present a key": "El servidor no presentó ninguna clave",
    "The server presented a different key than the one this connection trusts. If it was reinstalled, fetch its key again and compare it": "El servidor presentó una clave distinta de la que confía esta conexión. Si se reinstaló, obtén su clave de nuevo y compárala",
    "The server refused these credentials": "El servidor rechazó estas credenciales",
    "That is no longer on the server": "Eso ya no está en el servidor",
    "The server does not let this user do that": "El servidor no permite que este usuario haga eso",
    "The server could not do that": "El servidor no pudo hacerlo",
    "The server did not answer in time": "El servidor no respondió a tiempo",
    "Could not reach the server": "No se pudo contactar con el servidor",
    "Not a path below this folder: {path}": "No es una ruta dentro de esta carpeta: {path}",
    # Archivos por SFTP.
    "Symbolic links are not downloaded": "Los enlaces simbólicos no se descargan",
    "A folder holding a symbolic link is not copied here": "Una carpeta que contiene un enlace simbólico no se copia aquí",
    "What came out": "Resultado",
    "The file is no longer open": "El archivo ya no está abierto",
    "The file could not be read from the server": "No se pudo leer el archivo del servidor",
    "The file could not be created on the server": "No se pudo crear el archivo en el servidor",
    "The file could not be written on the server": "No se pudo escribir el archivo en el servidor",
    "The file could not be put in place on the server": "No se pudo colocar el archivo en su sitio en el servidor",
    # La terminal.
    "The server did not open a shell for this account": "El servidor no abrió un Shell para esta cuenta",
}
