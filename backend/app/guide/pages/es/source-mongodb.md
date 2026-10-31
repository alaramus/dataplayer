# MongoDB

Un servidor MongoDB. Exploras sus bases de datos y colecciones y lees los
documentos página a página como filas; los campos de una colección se deducen
de sus documentos. Cómo funcionan las conexiones en general se explica en la
página [Conexiones](connections.md).

## Qué puedes ver

- Bases de datos, colecciones, vistas y series temporales
- Documentos como filas, ordenados y filtrados por el servidor
- Los campos de los documentos de una colección y sus índices
- La definición de una colección: opciones, validador e índices, en JSON
- Cada documento entero, en JSON, página a página
- Cuántos documentos tiene una colección y cuánto espacio ocupa
- mongosh, con la sesión de la conexión, en un terminal
- Todos los documentos que coinciden, descargados en un archivo
- Las operaciones, conexiones, usuarios y roles del servidor
- Los contadores del servidor, en un panel

## Qué puedes cambiar

- Documentos: editar campos, pegar bloques, añadir y eliminar documentos
- Un campo en todos los documentos: añadir, quitar, renombrar, cambiar de tipo
- Índices: simples y únicos, hash, de texto y geoespaciales
- Bases y colecciones: crear, renombrar, mover, eliminar; cargar un CSV
- Una operación en curso: detenerla desde su informe
- Colecciones copiadas a otra conexión MongoDB con sus índices
- La base de la conexión: guardada en un archivo y restaurada desde él
- Todo lo que mongosh puede cambiar, en su terminal

## Conexión

La página **Conexión** de la ventana pide:

- **Host** y **Puerto** de un servidor, 27017 salvo que escuche en otro;
- **TLS**: una conexión cifrada, con el certificado del servidor verificado;
- **Autenticación**: usuario y contraseña, o ninguna para un servidor sin
  control de acceso. La **Base de datos de autenticación** es donde se creó el
  usuario, `admin` salvo que sea otra;
- **Base de datos**: dónde se abre el catálogo. Puede quedar vacía.

Una cadena de conexión como `mongodb://ann@db.example.com:27017/shop` pegada
en **URL** rellena estos campos; también se leen `?authSource=` y `?tls=true`.

El servidor indicado es con el que se habla. Un miembro de un replica set se
lee tal cual; para cambiar datos, indica el primario. No se admiten una
dirección `mongodb+srv://` ni una lista de servidores. Se admite MongoDB 5.0 y
posteriores.

## Catálogo

- El primer nivel son las bases de datos. La que indica la conexión va
  primero, aunque aún esté vacía; `admin`, `local` y `config` son del servidor.
- Dentro de una base están sus colecciones y vistas, con su número de
  documentos y su tamaño.

## Documentos como filas

- Las columnas de una colección son los campos de sus documentos: los que
  declara su validador y los hallados en los cien primeros y los cien últimos
  documentos. `_id` va primero. Un campo visto solo en otro documento se
  muestra en su página, sin ordenar ni filtrar.
- Cada columna indica el tipo que contiene; si los documentos no coinciden, es
  mixta.
- Un ObjectId se muestra en hexadecimal, una fecha en UTC con `Z`, un objeto o
  un array como JSON tal como lo escribe `mongosh`.
- Un campo ausente y uno con null muestran ambos una celda vacía.
- Un valor de filtro se lee como el campo guarda sus valores; un texto que
  parece una consulta es solo texto.
- Sin un orden tuyo, la página se ordena por `_id`.

## Cambiar documentos

- Una celda es un campo de un documento; lo que escribes se guarda como el
  campo guarda sus valores, un objeto o un array como JSON.
- Un documento cambiado desde que se leyó la página no se sobrescribe: se te
  avisa y la página se vuelve a leer.
- `_id` no se puede cambiar. Vaciar una celda guarda null.
- Un bloque pegado se comprueba entero y luego se escribe documento a
  documento; un bloque de documentos nuevos entra entero o no entra.
- **Ver como documentos** muestra cada documento entero.

## Estructura

Las columnas de una colección son los campos de sus documentos, así que la
pantalla de estructura cambia todos los documentos a la vez. Un cambio de tipo
cuenta antes los valores que no se pueden convertir y no cambia nada si hay
alguno. Un índice único no se crea si los valores se repiten.

## Acciones del catálogo y sección Server

- **Nueva base de datos** pide también el nombre de su primera colección.
- Una colección se renombra, se mueve a otra base o se elimina; una vista solo
  se puede eliminar.
- **Cargar desde CSV** crea una colección cuyos valores son texto.
- La sección **Server** contiene Operaciones, Conexiones, Usuarios y Roles;
  **Detener la operación** detiene lo elegido en Operaciones.

## Copias, copias de seguridad y un servidor propio

- **Copiar tablas** copia colecciones a otra conexión MongoDB, con sus
  opciones, cada documento y sus índices.
- Una copia de seguridad es el archivo de `mongodump`; la restauración usa
  `mongorestore`. No a través de un túnel SSH.
- **Servicios** puede iniciar un MongoDB propio y llenarlo con `demo_lab`.

## mongosh

**Abrir un terminal** en una conexión MongoDB tuya inicia `mongosh`, con la
sesión de la conexión, en un contenedor que inicia este servidor; no a través
de un túnel SSH. Cerrar el terminal o `exit` lo termina.
