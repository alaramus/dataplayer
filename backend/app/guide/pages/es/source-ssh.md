# SSH

Un servidor al que llegas por SSH. Exploras sus carpetas y trabajas con sus
archivos como con los tuyos: tablas, SQL sobre archivos, el editor, archivos
comprimidos, búsqueda, copia entre conexiones y una terminal. Inicia sesión con
una contraseña o con una de tus claves SSH, y solo en el servidor cuya clave
confirmaste. El funcionamiento general de las conexiones está en la página
[Conexiones](connections.md).

## Qué puedes ver

- Las carpetas y los archivos del servidor, desde donde elijas
- Tablas en archivos CSV, TSV, Excel y Parquet, y en archivos de registro
- Documentos, código, imágenes, PDF, grabaciones y el contenido de archivos ZIP
- Archivos encontrados por nombre, o por el texto que contienen
- SQL ejecutado sobre tablas guardadas en archivos

## Qué puedes cambiar

- Archivos en un editor de texto
- Las filas y columnas de archivos CSV y TSV
- Archivos y carpetas: crear, subir, renombrar, eliminar, descargar
- Archivos comprimidos: empaquetar archivos en uno, o descomprimir uno
- Archivos copiados o movidos entre carpetas y conexiones
- Cualquier otra cosa, desde una terminal en el servidor

## Conectar

La página **Conexión** de la ventana pide:

- **Host** y **Puerto**, 22 a menos que el servidor indique otra cosa;
- **Usuario**: la cuenta con la que iniciar sesión;
- **Carpeta**: dónde empieza la exploración. Vacío es la carpeta personal de la
  cuenta;
- **Clave del servidor**: con qué se identifica el servidor (ver más abajo);
- **Autenticación**: una contraseña, o **Clave**, una de tus claves SSH.

Una cadena de conexión como `ssh://ann@files.example.com:22` pegada en **URL**
rellena el host, el puerto y el usuario. Una contraseña nunca forma parte de
ella.

### La clave del servidor

No se envía nada a un servidor hasta que hayas confirmado su clave. Esto es lo
que impide que una contraseña o una clave vaya a una máquina que solo finge ser
la tuya.

1. Rellena el host y el puerto, y pulsa **Obtener del servidor**.
2. Se muestra la huella del servidor. Compárala con la que te da el administrador
   del servidor, o con la que imprime `ssh-keyscan`.
3. Pulsa **Confiar en esta clave**.

Un servidor que más tarde presenta una clave diferente se rechaza, con una frase
que lo indica. Si el servidor se reinstaló, obtén su clave de nuevo, compárala y
pulsa **Confiar en la nueva clave**. Solo el propietario de la conexión puede
hacerlo.

Un servidor iniciado desde **Iniciar servidor SSH aquí** confía en la clave que
presentó primero, porque esta aplicación lo inició.

### Claves SSH

Tus claves SSH están en la página **Preferencias**, aparte de las conexiones,
para que una clave sirva a tantas conexiones como la apuntes.

- **Nueva clave** crea una clave en este servidor: ED25519, o ESA para servidores
  que rechazan ED25519. **Importar** toma una clave privada que pegas o eliges
  como archivo.
- **Copiar la clave pública** copia la línea que hay que añadir a
  `~/.ssh/authorized_keys` en el servidor. Termina en `dataplayer`, para que el
  propietario del servidor pueda saber qué línea es.
- La mitad privada de una clave nunca se vuelve a mostrar, a nadie.
- Una clave puede tener una frase de contraseña, guardada de una de tres formas:
  ninguna; almacenada junto a la clave; o pedida cuando se necesita la clave y
  retenida durante 15 minutos, una hora u ocho horas. **Bloquearla ahora** la
  olvida antes de tiempo.
- Una clave bloqueada detiene sus conexiones. Cada pantalla que lee la conexión
  ofrece entonces **Desbloquear la clave** en lugar de un error.
- Una clave usada por una conexión no se puede eliminar. Primero apunta la
  conexión a otra clave.

## El catálogo y los archivos

Una conexión SSH se explora exactamente como una conexión de
[Archivos](source-file.md): el mismo catálogo, la misma búsqueda por nombre y
dentro de los archivos, los mismos visores, el mismo editor, las mismas acciones
(**Nueva carpeta**, **Nuevo archivo**, **Subir archivos**, **Renombrar**,
**Eliminar**, **Descargar**, **Archivar**, **Extraer**, **Copiar**, **Cortar**,
**Pegar**) y el mismo SQL sobre archivos.

Nada ejecuta un comando en el servidor para esto: todo pasa por SFTP.

Diferencias con tus propios archivos:

- **Conectar carpeta** no se ofrece.
- Un archivo de más de 200 MB no se abre como tabla, libro de trabajo, archivo
  comprimido ni en SQL: descárgalo en su lugar. El texto, las imágenes, los PDF y
  las grabaciones se abren sea cual sea su tamaño.
- Una búsqueda dentro de archivos omite los archivos de más de 1 MB y se detiene
  tras 32 MB en total, porque cada byte cruza la red.

## La terminal

**Terminales**, en la barra de herramientas izquierda, abre una terminal en el
panel del pie de la pantalla: el Shell de inicio de sesión de la cuenta de la
conexión, en el servidor.

- Solo el propietario de la conexión puede abrir una. Las personas con las que se
  comparte la conexión no pueden.
- El Shell empieza en la carpeta personal de la cuenta, no en la **Carpeta** de
  la conexión.
- Cerrar la terminal, cerrar la página o perder la red termina el Shell. No se
  vuelve a conectar; abre otra.
- Se pueden abrir varias terminales a la vez, hasta ocho. Cambiar a otra
  herramienta en el panel las mantiene en ejecución.
