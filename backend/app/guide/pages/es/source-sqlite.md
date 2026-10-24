# SQLite

Un archivo de base de datos SQLite en tu almacenamiento personal. Recorres sus
tablas y vistas, lees y editas sus filas página a página, ves cómo está
construida una tabla, lees el DDL que el archivo guarda para ella y ejecutas
SQL en una consola. Cómo funcionan las conexiones en general se explica en la
página [Conexiones](connections.md).

## Qué puedes ver

- Tablas, vistas y tablas virtuales, y sus filas ordenadas y filtradas
- Las columnas, claves, comprobaciones e índices de una tabla, y sus destinos
- El DDL de una relación, como lo guarda el archivo, con índices y disparadores
- Los resultados del SQL que escribes, y el plan de SQLite para una consulta
- Todas las filas que coinciden, descargadas en un archivo
- Lo que dice el archivo: estructura, integridad, claves rotas, disparadores
- Adónde lleva la clave foránea de una fila, y qué apunta a ella

## Qué puedes cambiar

- Datos de la tabla: editar celdas, pegar bloques, insertar y eliminar filas
- Columnas, índices, claves únicas y claves foráneas
- Tablas nuevas, diseñadas objeto por objeto o creadas a partir de filas
- Tablas y vistas: renombrar, eliminar
- Tablas copiadas con su estructura, a otro archivo SQLite o a este
- El archivo entero, con copia de seguridad y restauración
- Datos y estructura, mediante SQL en la consola

## Conectarse

La página **Conexión** de la ventana pide:

- **Archivo de base de datos**: la ruta del archivo dentro de tu almacenamiento
  personal, como `data/shop.db`. Pon el archivo allí primero, mediante una
  conexión **Archivos**. Una ruta fuera de tu almacenamiento se rechaza.
- **Crear el archivo si no existe**: márcalo para empezar con una base de datos
  vacía. Sin ello, un archivo que no está hace fallar la comprobación, así que
  una ruta mal escrita no deja un archivo vacío. La carpeta ya debe existir.

Un archivo de base de datos que ya ves en una conexión **Archivos** se puede
conectar desde allí: **Conectar como SQLite** rellena esta ventana por ti.

El archivo se abre de nuevo en cada petición, así que un archivo reemplazado
mediante **Archivos** se lee tal como está ahora.

Lo que una conexión al archivo no puede hacer, contenga lo que contenga el
archivo: abrir un segundo archivo (`ATTACH`, `VACUUM INTO`), cargar una
extensión o alcanzar cualquier otra cosa del servidor. Cualquiera puede subir
un archivo, así que una vista o un disparador dentro de él tampoco puede llamar
a una función con efectos secundarios.

## Una base propia

**Nueva conexión** ofrece **Crear SQLite aquí**, de las dos maneras en que se
inicia un servidor. **Configúralo por mí** crea `databases/dataplayer.db` en tu
almacenamiento, lleno con un laboratorio de organizaciones, personas, proyectos
y tareas, y guarda la conexión por ti. **Déjame elegir** pregunta el nombre, la
carpeta, si llenarlo y si usar el registro de escritura anticipada (WAL). Un nombre ya usado recibe un número en lugar de reemplazar el archivo.
El archivo es uno normal: se renombra, descarga o elimina en **Archivos**.

## El catálogo

- El primer nivel es `main`, el único esquema del archivo.
- Dentro están sus tablas, vistas y tablas virtuales. Al pulsar una se abren
  sus filas en una pestaña.
- Las tablas propias de SQLite (`sqlite_schema`, `sqlite_sequence`,
  `sqlite_stat1`) y las que una tabla virtual mantiene para sí misma, como las
  de un índice de texto completo, se marcan como tablas del sistema.
- Una tabla dice aproximadamente cuántas filas tiene solo después de ejecutar
  `ANALYZE` sobre el archivo. Nada cuenta las filas.
- **Detalles** dice cuántas columnas, índices y restricciones tiene una
  relación.
- **Mostrar DDL** muestra la instrucción `CREATE TABLE` o `CREATE VIEW` que
  guarda el archivo, seguida de los índices y disparadores de la tabla.
- Una tabla virtual hecha con un módulo que este servidor no tiene aparece en
  la lista y lo dice al abrirla.
- **Sistema**, después de `main`, es una sección de informes (consulta
  **Informes** más abajo).
- La búsqueda de la cabecera encuentra tablas y vistas por su nombre y por sus
  columnas.

## Leer filas

Una tabla se abre como cuadrícula, una página cada vez, ordenada y filtrada
como una tabla de PostgreSQL. Todas las columnas se pueden ordenar. Lo que
ofrece una columna depende del tipo con el que se declaró: comparaciones para
números, fechas y texto; contiene y empieza por para texto; vacío o no vacío
para todas las columnas.

- Las páginas siguen la clave primaria o, si no la hay, el orden en que se
  escribieron las filas (el `rowid`). Una vista viene en el orden que devuelve
  SQLite.
- Un `%` o `_` escrito en un filtro de texto se busca tal cual. Los filtros de
  texto no distinguen mayúsculas de minúsculas en las letras latinas.
- Una columna declarada sin tipo se filtra como texto.

Cómo se muestran los valores:

- un valor como lo que es, diga lo que diga su columna: SQLite deja que una
  columna `INTEGER` contenga texto, y el texto se muestra como texto;
- los valores binarios en hexadecimal, como `0x00FF`, en cualquier columna;
- una columna `BOOLEAN` como `true` o `false` donde contiene 0 o 1;
- el texto que no es UTF-8 válido en hexadecimal, en lugar de con caracteres
  que no están;
- los enteros grandes con exactitud.

## Cambiar filas

Con acceso **Editar filas**, una tabla se edita en su cuadrícula como una tabla
de PostgreSQL: doble clic en una celda, pegar un bloque, **Insertar fila**,
marcar filas y **Eliminar las filas seleccionadas**. Las vistas, las tablas
virtuales y las tablas propias de SQLite son de solo lectura, y una columna
generada se calcula en lugar de escribirse.

- Una fila se vuelve a encontrar por su clave primaria, o por su `rowid` cuando
  la tabla no tiene.
- Si alguien cambió una fila después de que la leyeras, en cualquier columna,
  tu cambio se rechaza en lugar de escribirse sobre el suyo. Recarga e inténtalo
  de nuevo.
- Escribe los valores como los muestra la cuadrícula: binario como `0x…` en una
  columna `BLOB`, `true` o `false` en una `BOOLEAN`. Una columna sin tipo
  mantiene un número como número. Lo que recibe cualquier otra columna, SQLite
  lo guarda convertido como dice su tipo.
- Una tabla `STRICT` rechaza un valor del tipo equivocado antes de escribir
  nada, y se nombran las celdas que contienen esos valores. Nada de un bloque
  pegado llega hasta que puede llegar todo.
- Un cambio que rechazan las claves, comprobaciones o columnas obligatorias de
  la tabla no se hace, y dice qué regla lo rechazó. Las claves foráneas del
  archivo se aplican.
- Una celda de una clave foránea tiene una flecha que abre la fila a la que
  apunta, y **Qué apunta a esta fila** abre las filas que apuntan aquí.

## Cambiar la estructura

**Estructura** de una tabla la cambia como cambia una tabla de PostgreSQL:
añadir, renombrar y eliminar una columna, fijar o quitar su valor por defecto,
exigir un valor o dejar de exigirlo, cambiar su tipo, añadir y eliminar
índices, claves únicas y claves foráneas.

- SQLite por sí mismo solo puede añadir una columna que pueda quedar vacía y
  renombrar una. Para todo lo demás, la tabla se reconstruye como describe la
  documentación de SQLite: una tabla nueva, las filas copiadas con su `rowid`,
  la antigua reemplazada, sus índices y disparadores creados de nuevo. Lo que
  el cambio no toca — `AUTOINCREMENT`, `DEFERRABLE`, los comentarios — se
  conserva tal como está escrito.
- Un cambio que las filas ya contradicen no se hace, y se muestra el recuento:
  filas sin valor, valores que se repiten, filas que no apuntan a nada.
- Una columna con tipo acepta cualquier valor en SQLite, así que un cambio de
  tipo solo se rechaza en una tabla `STRICT`, con el recuento de valores que no
  puede contener.
- Eliminar una columna elimina las claves e índices sobre ella. Una
  comprobación o una vista que lee la columna rechaza la eliminación, y dice
  cuál.
- Los tipos que se ofrecen son los de SQLite: texto, entero, coma flotante,
  número, booleano, fecha, fecha y hora, JSON, UUID y binario. A una tabla
  `STRICT` se le ofrecen los suyos: texto, entero, coma flotante, binario y
  cualquier valor.
- SQLite construye un solo tipo de índice, un árbol B, y nombra lo que crea
  según la tabla y sus columnas.

## Crear una tabla

**Crear tabla** en el menú de acciones de `main` abre el diseñador de tablas,
como en PostgreSQL. El plan es un `CREATE TABLE` y un `CREATE INDEX` por
índice, ejecutados juntos: la tabla se crea entera o no se crea.

- Una columna de identidad es el número de fila propio de SQLite: un entero
  que es toda la clave primaria, escrito `INTEGER PRIMARY KEY AUTOINCREMENT`.
  Puede empezar en cualquier número, cuenta de uno en uno y acepta un valor que
  escribas en ella.
- Lo que SQLite no tiene se marca en el objeto que lo pide antes de que puedas
  revisar el plan: una tabla sin registro o particionada, una clave única
  comprobada al confirmar, nulos ordenados primero o al final, columnas extra
  llevadas por un índice.
- SQLite tiene lo que le falta a MySQL: un índice sobre parte de las filas, una
  clave foránea comprobada al confirmar, `SET DEFAULT` y un índice sobre una
  expresión.
- Los comentarios no se guardan; el plan lo dice.
- Las intercalaciones son las de SQLite: `BINARY`, `NOCASE` y `RTRIM`.
- Las filas guardadas como tabla, o un archivo cargado en una, llegan con la
  tabla de una vez.

## Informes

**Sistema** en el catálogo contiene ocho informes. Se leen como tablas y se
pueden ordenar, filtrar, descargar y representar en gráficos. **Mostrar la
instrucción** muestra el SQL que ejecuta un informe.

- **Archivo**: el tamaño y el número de páginas, el tamaño del archivo, las
  páginas libres, la codificación, el modo de diario, el auto-vacuum y los
  números de versión que guarda el archivo.
- **Integridad**: la comprobación rápida de cada página por SQLite: `ok`, o lo
  que está dañado. Lee el archivo entero, así que solo se lee al abrirlo.
- **Claves foráneas rotas**: filas cuya clave no apunta a nada, escritas por un
  programa que no las aplicaba.
- **Disparadores**, con sus definiciones.
- **Funciones**, **Módulos** e **Intercalaciones** que ofrece el SQLite de este
  servidor, y las **Opciones de compilación** con las que se construyó.

## Acciones del catálogo

- **Renombrar** una tabla o una vista. Lo que hace referencia a una tabla la
  sigue. Una vista se crea de nuevo con el nombre nuevo; una vista que la lee
  por su nombre antiguo rechaza el cambio de nombre y se nombra.
- **Eliminar** una relación o varias juntas. La eliminación se prueba primero y
  se deshace, así que la pregunta muestra lo que haría: los disparadores que se
  van con ella, las tablas que apuntan a ella, las vistas que la leen. Si una
  tabla que apunta a ella aún tiene filas y no elimina en cascada, la
  eliminación se rechaza por ese motivo. Las tablas que se apuntan entre sí se
  pueden eliminar juntas.
- **Cargar desde CSV** crea en `main` una tabla a partir de un archivo, con
  cada columna como `TEXT`.
- **Modelo como código** escribe `main` o una selección para un ORM o un
  diagrama.

## Copiar tablas

**Copia** tablas en el catálogo y **pégalas** en `main` de otra conexión SQLite,
o de esta. Llegan con sus columnas tal como las escribe el archivo, sus claves,
comprobaciones, índices y opciones como `STRICT`; la ventana pregunta lo mismo
que en PostgreSQL, muestra cada instrucción y no ejecuta nada antes de
**Copiar**.

- Los disparadores se quedan atrás, nombrados en la ventana. Las vistas y las
  tablas virtuales no se copian así.
- Un índice recibe el nombre de la tabla nueva, porque dos índices de un mismo
  archivo no pueden compartir nombre.
- La copia es una sola transacción: las tablas, sus filas y sus índices llegan
  juntos o no llegan. Una fila cuya clave foránea no apunta a nada en la copia
  la hace fallar al final, y no queda nada.

Las filas pegadas en una conexión de otro tipo siguen el camino de las filas de
cualquier tabla.

## Copias de seguridad

**Copias de seguridad**, en el menú de acciones del catálogo, funciona como en
PostgreSQL, para el archivo que abre la conexión.

- La copia de seguridad es una copia del archivo hecha por el propio SQLite,
  así que está completa aunque alguien esté escribiendo en el archivo.
- **Restaurar** reemplaza todo lo que hay en el archivo por la copia. Un archivo
  que no es una base de datos SQLite, o que SQLite considera dañado, se rechaza
  antes de escribir nada.

## Consola SQL

**Nueva consulta** en **Consultas** de la barra izquierda inicia una en la
conexión, y **Abrir como consulta** sobre una tabla inicia una en esa tabla.
Funciona como la consola de PostgreSQL — lecturas, cambios confirmados en el
acto o retenidos en una transacción **Manual**, **Explicar**, autocompletado y
formato. SQLite cambia la estructura dentro de una transacción, así que un
`CREATE`, `ALTER` o `DROP` forma parte de la transacción que lo rodea, se puede
retener en una manual y se prueba primero y se deshace antes de que la consola
te pregunte.

- El esquema es siempre `main`.
- Los parámetros se escriben `:name`.
- `ANALYZE`, `VACUUM` y `REINDEX` se ejecutan solos, fuera de una transacción.
- Un `PRAGMA` que informa de algo, como `PRAGMA table_info(items)` o
  `PRAGMA integrity_check`, es una lectura. Un `PRAGMA` que fija un valor no se
  ejecuta.
- Las claves foráneas que declara el archivo se aplican, cosa que SQLite por sí
  solo hace solo cuando un programa se lo pide.
- Los disparadores no se cambian desde la consola, y no se puede abrir ningún
  otro archivo desde ella (`ATTACH`).
- **Explicar** muestra el plan de SQLite: una línea por paso, sin costes, ya
  que SQLite no los da.
- **Detener** y el límite de tiempo terminan una instrucción donde esté.
- Una instrucción fallida dentro de una transacción que retienes deja la
  transacción abierta.

## Lo que SQLite aún no tiene aquí

- Un archivo en un servidor SSH, o dentro de otra conexión, no se puede abrir
  como base de datos.
