# FTP

Un servidor al que se llega por FTP o FTPS. Exploras sus carpetas desde donde
elijas y trabajas con sus archivos como con los tuyos: tablas, SQL sobre
archivos, visores y búsqueda. Inicia sesión con contraseña o de forma anónima.
Cómo funcionan las conexiones en general está en la página
[Conexiones](connections.md).

## Qué puedes ver

- Carpetas y archivos bajo la carpeta que elijas
- Tablas en archivos CSV, TSV, Excel y Parquet, y en registros
- Documentos, código, imágenes, PDF, grabaciones y el interior de archivos zip
- Archivos encontrados por nombre o por el texto que contienen
- SQL ejecutado sobre tablas guardadas en archivos

## Qué puedes cambiar

- Archivos en un editor de texto
- Las filas y columnas de archivos CSV y TSV
- Archivos y carpetas: crear, subir, renombrar, eliminar, descargar
- Archivos comprimidos: empaquetar archivos en uno o descomprimir uno
- Archivos copiados o movidos entre carpetas y conexiones

## Conectar

La página **Conexión** de la ventana pide:

- **Host** y **Puerto**: 21, o 990 para TLS implícito;
- **Cifrado**: **TLS, explícito** es lo que hablan hoy la mayoría de los
  servidores, en el puerto 21. **TLS, implícito** es el FTPS antiguo en el
  puerto 990. **Sin cifrado** envía la contraseña tal como la escribes: elígelo
  solo para un servidor que no ofrece otra cosa;
- **Verificar el certificado**: desactívalo solo para un servidor con un
  certificado hecho por ti;
- **Carpeta**: dónde empieza la navegación. Vacío es la carpeta en la que el
  servidor te deja al entrar; `/` es la raíz del servidor;
- **Autenticación**: un **Usuario** y una **Contraseña**, o **Anónimo** para un
  servidor público.

**URL** muestra el servidor como `ftp://user@host/folder`, y `ftps://` para TLS
implícito. Una dirección pegada ahí rellena el host, el puerto, el usuario y la
carpeta. La contraseña nunca forma parte de ella.

## El catálogo y los archivos

Una conexión FTP se explora como una conexión [Archivos](source-file.md): el
mismo catálogo, la misma búsqueda por nombre y dentro de los archivos, los mismos
visores y el mismo SQL sobre archivos. También las mismas acciones: **Nueva carpeta**, **Nuevo archivo**,
**Subir archivos**, **Renombrar**, **Eliminar**, **Descargar**, **Archivar**,
**Extraer**, **Copiar**, **Cortar** y **Pegar**.

En qué se diferencia un servidor FTP de un disco:

- Los permisos del propio servidor deciden qué puedes leer y cambiar.
- Un archivo cuyo nombre no está en UTF-8 no se muestra. Sigue en el servidor.
- Algunos servidores dan la hora solo al minuto, o solo el día para archivos
  antiguos, y ninguno dice su zona horaria: las horas se muestran en UTC.
- Un archivo de más de 200 MB no se abre como tabla, libro, archivo comprimido
  ni en SQL: descárgalo. Texto, imágenes, PDF y grabaciones se abren sea cual
  sea su tamaño.
- Una búsqueda dentro de archivos omite los de más de 1 MB y se detiene tras
  32 MB en total, porque cada byte cruza la red.
- Copiar hace pasar cada byte por DataPlayer, porque FTP no tiene copia propia:
  hasta 200 MB de una vez.
- Un archivo guardado sobre otro que cambió mientras tanto se rechaza en lugar
  de sobrescribirse.
