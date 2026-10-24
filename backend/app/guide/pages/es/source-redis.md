# Redis

Un servidor de clave-valor en memoria. Recorres sus claves como un árbol formado
por los dos puntos de sus nombres, lees lo que contiene una clave como filas,
escribes claves de todos los tipos y estableces o quitas su caducidad. El
funcionamiento general de las conexiones está en la página
[Conexiones](connections.md).

## Qué puedes ver

- Todas las bases de datos del servidor, y sus claves como un árbol
- Lo que contiene una clave, como filas: campos, elementos de lista, miembros,
  puntuaciones, entradas
- El tipo de una clave, su tamaño y el tiempo que le queda de vida
- Una carpeta de haches como una sola tabla
- Métricas del servidor en cuadros de mando

## Qué puedes cambiar

- Los valores dentro de una clave, uno a la vez
- Claves de los seis tipos: crear, reemplazar, eliminar
- La caducidad de una clave: establecerla o quitarla
- Tablas descritas sobre carpetas de haches
- Claves guardadas como archivos CSV

## Conectar

La página **Conexión** de la ventana pide:

- **Host** y **Puerto**, 6379 a menos que el servidor indique otra cosa;
- **Base de datos**: la que abre el catálogo. Todas las bases de datos siguen
  siendo accesibles desde el catálogo;
- **Autenticación**: una contraseña, o ninguna.

Una cadena de conexión como `redis://:secret@cache.example.com:6379/0` pegada en
**URL** rellena estos campos. Una dirección `rediss://`, que necesita TLS, aún no
es compatible.

## El catálogo

El catálogo es un árbol.

- El control de la parte superior elige la base de datos. Indica cuántas claves
  contiene cada una. La elección se recuerda en este navegador.
- Las claves se agrupan por los dos puntos de sus nombres: `session:42:token` está
  bajo `session`, luego `42`. Pulsar una carpeta la abre donde está.
- Una clave indica su tipo, su tamaño y cuánto le queda, si caduca.
- Pulsar una clave la abre en una pestaña. Pulsar una fila la selecciona, y el
  menú de acciones actúa entonces sobre ella.
- Un espacio de claves muy grande se enumera hasta un límite. Una carpeta más
  concreta muestra lo que hay más allá.

## Leer una clave

Una clave se abre como filas. La forma depende de su tipo:

- una **cadena** es un valor;
- un **has** son campos y valores;
- una **lista** son posiciones y valores;
- un **conjunto** son miembros;
- un **conjunto ordenado** son miembros y puntuaciones;
- un **flujo** son entradas.

Las filas se paginan como cualquier tabla de la cuadrícula. Redis no tiene un
índice sobre los valores, así que nada se puede ordenar ni filtrar. **Descargar**
puede guardar todas las filas como un archivo CSV.

## Editar una clave

Con acceso **Editar filas**, los valores de una clave se editan en su cuadrícula:

- haz doble clic en una celda para cambiar un campo de has, un elemento de
  lista, una cadena o una puntuación;
- **Insertar fila** añade un campo, un elemento, un miembro;
- marca filas y **Eliminar las filas seleccionadas** quita campos y miembros.

Lo que permite cada tipo lo muestra la propia cuadrícula. No se puede quitar un
elemento del medio de una lista, y un flujo no se puede editar en absoluto.

Si alguien cambió el valor después de que lo leyeras, se rechaza tu cambio en
lugar de escribir encima del suyo. Recarga e inténtalo de nuevo.

## Escribir claves

Selecciona una carpeta o una clave en el árbol y abre el menú de acciones:

- **Nueva cadena**, **Nuevo has**, **Nueva lista**, **Nuevo conjunto**, **Nuevo
  conjunto ordenado**, **Nuevo flujo**. El nombre que escribes se añade a la
  carpeta en la que estás, así que `one` escrito en `cache:` se convierte en
  `cache:one`. Una colección se escribe con un miembro, o un `name=value`, por
  línea. Se puede establecer una caducidad de inmediato. Un nombre ya en uso se
  rechaza a menos que elijas reemplazarlo;
- **Eliminar** quita una clave, después de preguntar;
- **Establecer caducidad** da a una clave un tiempo de vida, y **Quitar
  caducidad** lo retira.

## Copiar fuera

**Copiar** una clave, una carpeta o una base de datos en el catálogo y **Pegar**
en una carpeta de una conexión de archivos o SSH: cada una se convierte en un
archivo CSV. Varias marcadas se copian juntas, un archivo cada una. También puedes
exportar todas las filas de una clave, carpeta o base de datos como CSV.

## Métricas

Una conexión Redis puede informar de sus propios contadores a los cuadros de
mando: memoria, clientes, comandos, aciertos y fallos, claves caducadas y
expulsadas, tráfico de red y claves por base de datos. El propietario lo activa
en la ventana **Fuentes** del espacio **Cuadros de mando**, y elige la
frecuencia. El diseño preparado para ello se llama **Servidor Redis**.

## Lo que Redis no tiene aquí

- No hay consola de comandos: Redis recibe comandos en lugar de instrucciones, y
  una consola para ellos sería un Shell en el servidor.
- Una clave que caduca mientras su pestaña está abierta permanece en pantalla
  hasta que se vuelve a leer la pestaña.
- Los valores se muestran como texto. Una clave que contiene una imagen se muestra
  como caracteres ilegibles.
