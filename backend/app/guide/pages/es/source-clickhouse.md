# ClickHouse

Un servidor ClickHouse al que se accede mediante su interfaz HTTP. Puede
explorar sus bases de datos, leer tablas y vistas página por página, consultar
cómo está construida una tabla, ver su DDL tal como lo escribe el servidor y
ejecutar SQL en una consola.
La página [Conexiones](connections.md) explica cómo funcionan las conexiones
en general.

## Qué puedes ver

- Bases de datos, tablas, vistas y vistas materializadas
- Filas ordenadas y filtradas por el servidor, con sus valores exactos
- Columnas, claves, índices de omisión y comprobaciones
- DDL de una relación tal como lo escribe el servidor
- Tamaño, particiones y última escritura de una tabla
- Resultados de su SQL y el plan de la consulta del servidor
- Todas las filas coincidentes, descargadas en un archivo
- Consultas, mutaciones, fusiones, tamaños de tablas, discos y ajustes
- Contadores del servidor en un panel

## Qué puedes cambiar

- Datos de tablas: editar celdas, pegar bloques, insertar y eliminar filas
- Columnas e índices de omisión de tablas MergeTree
- Tablas nuevas, diseñadas objeto por objeto o creadas desde filas
- Bases de datos: crearlas y eliminarlas
- Tablas y vistas: renombrarlas, moverlas o eliminarlas
- Copiar tablas con su estructura a otra conexión ClickHouse
- Copias de seguridad y restauración de la base de datos de la conexión
- Datos y estructura mediante SQL, un cambio por ejecución

## Conexión

La página **Conexión** de la ventana solicita:

- **Host** y **Puerto** de la interfaz HTTP: 8123 o 8443 con TLS. No se usa el
  puerto nativo 9000;
- **TLS**: HTTPS con verificación del certificado del servidor. ClickHouse
  Cloud lo necesita;
- **Autenticación**: usuario y contraseña, o un usuario sin contraseña. Si no
  indica otro, el usuario es `default`;
- **Base de datos**: dónde se abre el catálogo. Puede dejarla vacía. El catálogo
  muestra de todos modos todas las bases que el usuario puede ver.

Una cadena de conexión como `clickhouse://ann@ch.example.com:8123/logs`, pegada en **URL**, rellena estos campos. También se reconoce `https://ch.example.com:8443`
 y `?secure=true` activa TLS. La contraseña incluida se copia al campo de
contraseña y se elimina de la cadena.

Se admite ClickHouse 23.8 y versiones posteriores. Se rechaza un servidor más
antiguo al comprobar la conexión y se indica su versión. No se puede usar un
usuario con el perfil `readonly = 1`: cada lectura envía sus propios ajustes,
que ese usuario quizá no tenga permitido establecer.

## Catálogo

- El primer nivel contiene las bases de datos. La indicada en la conexión
  aparece primero; `system` e `information_schema` pertenecen al servidor y se
  marcan como tales.
- Dentro de una base están sus tablas, vistas y vistas materializadas. La tabla
  donde una vista materializada guarda sus filas no aparece junto a ella: se
  lee a través de la vista.
- En las tablas MergeTree, el servidor indica cuántas filas hay y su tamaño.
  Los demás motores no proporcionan esos datos.

## Lectura de filas

- Los números se muestran exactamente como están almacenados, hasta el último
  dígito de un `UInt256` o un `Decimal`.
- Todos los instantes se muestran en UTC con `Z`, sea cual sea la zona horaria
  de la columna. Un filtro sin desplazamiento horario también se interpreta en
  UTC.
- Los arrays, mapas y tuplas se muestran como JSON.
- Las columnas de texto con bytes que no sean UTF-8 muestran caracteres de
  reemplazo.
- En ClickHouse ninguna clave es única. Por eso, una página de tabla se ordena
  primero por su clave de ordenación y después por todas las demás columnas; la
  siguiente página no repite la última fila. Las tablas cuyo motor lee datos
  externos —de una URL, un archivo o un flujo— o que no terminan, como
  `system.numbers`, se leen en el orden que proporciona el motor.

## Cambiar filas

- En una tabla MergeTree puede editar celdas, pegar bloques, insertar y eliminar
  filas. Las tablas Log, TinyLog, StripeLog, Memory, Buffer y Distributed solo
  admiten filas insertadas. Las vistas, las tablas que leen datos externos y
  las tablas del propio servidor no admiten cambios.
- ClickHouse no tiene una clave que distinga las filas, así que una fila se
  localiza mediante todos sus valores. Para quien las lee, las filas iguales en
  cada valor son una sola: editar una modifica todas y eliminar una las elimina
  todas. El recuento posterior indica cuántas se eliminaron.
- Una fila que solo difiere de otra en una columna de coma flotante, Map o JSON
  no se puede distinguir de ella y no se modifica. Se muestra el motivo.
- Si alguien modifica una fila después de que usted la haya leído, se rechaza su
  cambio en lugar de sobrescribir el suyo. Vuelva a leer la página y repita el
  cambio. No se detecta un cambio hecho en el mismo instante: ClickHouse no
  tiene una transacción que mantenga la fila bloqueada.
- No se editan las columnas de las claves de ordenación, primaria o de
  partición, las columnas calculadas ni las columnas Map o JSON. ClickHouse usa
  la clave para decidir dónde guarda una fila y no puede moverla.
- El servidor interpreta cada valor según el tipo de su columna y lo rechaza si
  no cabe. Un bloque pegado se acepta entero o no se acepta, y se marcan las
  celdas incompatibles. Los instantes se interpretan en UTC, tal como aparecen;
  los arrays y las tuplas se escriben como el JSON que muestran.
- Una tabla creada con `enable_block_number_column` y
  `enable_block_offset_column` se modifica con un `UPDATE` ligero. Las demás se
  modifican mediante una mutación que reescribe las partes afectadas: adecuada
  para pocas filas, lenta al pegar cientos.
- Una fila nueva no tiene identificador hasta volver a leer la página, así que
  no se puede editar inmediatamente.

## Cambiar la estructura

- En una tabla MergeTree se pueden añadir, renombrar y eliminar columnas,
  asignarles un valor predeterminado, hacerlas obligatorias u opcionales y
  cambiarles el tipo. Se pueden crear y eliminar índices de omisión. No se
  modifican otros motores ni vistas.
- No se eliminan, renombran ni modifican las columnas de las claves de
  ordenación, primaria o de partición: ClickHouse usa la clave para decidir
  dónde guarda cada fila.
- Antes de cambiar el tipo, el servidor cuenta los valores que el nuevo tipo no
  admite. Antes de hacer obligatoria una columna, cuenta las filas sin valor.
  No se cambia nada mientras cualquiera de los recuentos sea mayor que cero:
  ClickHouse convierte las filas después de cambiar la columna y, si la
  conversión falla, la tabla quedaría ilegible. Si aun así falla, se detiene y
  se restaura el tipo anterior. Un valor que perdería información —`1.5` en un
  entero— cuenta como incompatible.
- Cambiar un tipo reescribe la tabla entera en el disco, así que tarda según el
  tamaño de la tabla.
- Un índice de omisión puede ser min-max, un conjunto de hasta cien valores o
  un filtro Bloom, sobre las columnas elegidas. También se crea para las filas
  existentes. Ninguno es único y no se puede eliminar la clave primaria.
- ClickHouse no tiene claves únicas ni claves foráneas que se puedan crear.

## Crear una tabla

- **Crear tabla** en una base de datos abre el diseñador de tablas. El plan, que
  se muestra antes de ejecutarse, es un solo `CREATE TABLE` para una tabla
  MergeTree.
- La clave primaria se convierte en la clave de ordenación: ClickHouse guarda
  las filas en ese orden y las encuentra mediante ella, pero no impide que dos
  filas compartan la clave. Sus columnas deben tener un valor. Sin una clave,
  las filas se guardan en el orden de llegada.
- Una columna que puede estar vacía es `Nullable`; las columnas de array o JSON
  siempre tienen un valor. Las columnas calculadas se calculan al escribir la
  fila.
- Ahora, hoy y un UUID aleatorio pueden rellenar un valor predeterminado o una
  columna calculada.
- ClickHouse no ofrece claves únicas ni foráneas, columnas de identidad,
  intercalaciones ni particiones por rango, lista o hash. El diseñador lo indica
  en el objeto que lo solicita.
- Una tabla creada desde las filas de una página es MergeTree y permite que
  todas sus columnas estén vacías. Si se rechazan sus filas, la tabla no se
  conserva.

## Sección System

- Después de las bases, **System** muestra lo que el servidor dice de sí mismo:
  **Processes**, **Mutations**, **Merges**, **Table sizes**, **Disks**,
  **Changed settings**, **Metrics** y **Users**. Se ordenan, filtran y paginan
  como una tabla. Processes, Mutations, Merges y Metrics se vuelven a leer cada
  pocos segundos.
- En **Processes**, elija consultas y **Cancel query** para detenerlas. Lo que
  una consulta ya haya escrito permanece escrito.
- En **Mutations**, **Stop mutation** detiene un cambio que está reescribiendo
  partes de una tabla. Una mutación que falla repetidamente bloquea los cambios
  posteriores de la tabla; el error aparece en la última columna. Al detenerla,
  la tabla vuelve a poder modificarse.
- La base `system` completa también aparece en el catálogo para consultar lo que
  estos informes no incluyen.

## Búsqueda y descarga

- El campo de búsqueda encuentra bases y tablas por nombre, y tablas por el
  nombre o comentario de una columna o por su propio comentario. `%` y `_` son
  caracteres normales.
- **Descargar** exporta todas las filas que coinciden con los filtros y el
  orden de la página, no solo las de la página actual.

## Acciones del catálogo

- **Nueva base de datos** en el nivel superior de la conexión.
- En una base: **Crear tabla**, **Cargar desde CSV**, **Eliminar base de datos**
  y **Modelar como código**. Solo se elimina una base después de ver qué
  contiene y marcar que se elimine todo.
- En una tabla o vista: **Renombrar**, **Mover a base de datos**, **Eliminar** y
  **Modelar como código**. Antes de eliminar, se indican las vistas
  materializadas que leen la tabla y dejarían de funcionar. No se indican las
  vistas normales: el servidor no guarda una lista de lo que lee cada vista.
- Un CSV se convierte en una tabla con columnas de texto que pueden estar vacías.
- El servidor no permite eliminar una tabla mayor que su límite, 50 GB salvo
  que el administrador lo haya cambiado, e indica el motivo.
- Aquí no se puede deshacer nada: ClickHouse guarda cada cambio al instante.

## Copiar tablas

**Copie** tablas en el catálogo y **péguelas** en una base de otra conexión
ClickHouse o de esta misma. Se copian con columnas, valores predeterminados,
columnas calculadas, códecs y comentarios, índices de omisión, comprobaciones,
motor, claves y ajustes. La ventana pregunta lo mismo que en PostgreSQL, muestra
todas las instrucciones y no ejecuta ninguna antes de **Copiar**.

- Se copian las tablas de la familia MergeTree y de los motores Log y Memory.
  No se copian las tablas replicadas, las vistas ni las tablas sobre archivos,
  URL, flujos u otros servidores; la ventana explica el motivo.
- Las vistas materializadas que leen una tabla copiada se quedan donde están y
  se indican en la ventana.
- Primero se crean las tablas y después se copian las filas. Si la copia falla
  o se detiene, se eliminan las tablas que creó.
- Las tablas no se bloquean durante la lectura: las filas escritas mientras
  tanto podrían copiarse o no.

Las filas pegadas en otro tipo de conexión se transfieren igual que las filas
de cualquier tabla.

## Copias de seguridad

**Copias de seguridad**, en el menú de acciones del catálogo, funciona como en
PostgreSQL para la base indicada en la conexión. No se ofrece si la conexión no
indica una base de datos.

- La copia es un único archivo de texto: la instrucción para crear cada tabla,
  vista y vista materializada, y todas las filas de cada tabla. El archivo
  enumera como omitidas las tablas de otros motores, por ejemplo las replicadas.
- Las tablas se leen una después de otra, no en un mismo instante.
- **Restaurar** elimina y vuelve a crear cada tabla y vista de la copia. Se
  conserva lo que haya en la base y no esté en la copia. Solo se restaura en una
  base con el mismo nombre y en la misma versión de ClickHouse o una posterior.

## Paneles

Una conexión ClickHouse puede enviar datos a los paneles. La disposición
**ClickHouse server** muestra conexiones y consultas en curso, consultas por
segundo, filas leídas, insertadas y fusionadas, memoria, tráfico de red, partes
activas, consultas fallidas y el tamaño de la base de la conexión. Los
contadores corresponden a todo el servidor.

## Su propio servidor

**Nueva conexión** ofrece **Iniciar ClickHouse aquí**: se inicia un servidor en
esta máquina y se guarda como una conexión que inicia sesión con su usuario
`default`. Ese usuario también puede administrar usuarios y permisos. Con los
datos de ejemplo, abre `demo_lab` —organizaciones, personas, proyectos y sus
tareas, además de doscientas mil visitas a páginas— con ejemplos para cada
pantalla: particiones, TTL, códecs e índices de omisión, ReplacingMergeTree y
SummingMergeTree, dos vistas materializadas alimentadas por las visitas, una
vista y una tabla Log.

## Consola SQL

**Nueva consulta**, en **Consultas** en la barra izquierda, inicia una consulta
en la conexión. **Abrir como consulta**, sobre una tabla, inicia una consulta
sobre esa tabla. Funciona como la consola de PostgreSQL —lecturas, cambios,
**Explain**, autocompletado y formato— con estas diferencias:

- La base elegida sobre el editor es la predeterminada; solo se elige una cada
  vez.
- No hay transacciones **Manual** ni se ensaya nada antes: ClickHouse guarda
  cada cambio al instante y no puede deshacerlo. Por eso, cada instrucción que
  inserta, elimina, altera o crea algo se ejecuta por separado. Ejecute los
  cambios de un script instrucción por instrucción; las lecturas pueden
  ejecutarse juntas.
- Una lectura usa el ajuste de servidor `readonly`, que hace que el servidor
  rechace cualquier escritura.
- `ALTER TABLE … DELETE` y `UPDATE` terminan antes que la instrucción, de modo
  que la siguiente lectura ya ve las filas cambiadas.
- Los parámetros siguen la sintaxis de ClickHouse, `{name:Type}`. El servidor
  interpreta el valor con ese tipo y rechaza el que no encaja; **SQL null**
  envía NULL a un tipo `Nullable`. El valor se interpreta como con `--param_` de
  clickhouse-client, así que una barra inversa inicia una secuencia de escape.
- `INSERT INTO t FORMAT JSONEachRow` seguido de sus filas funciona, al igual
  que `SHOW`, `DESCRIBE`, `EXISTS`, `CHECK TABLE` y `EXPLAIN AST`, `SYNTAX`,
  `PIPELINE` y `ESTIMATE`. Un `EXPLAIN` simple es **Explain**.
- No se ejecutan `SET` ni `USE` —añada `SETTINGS` a la instrucción y elija la
  base sobre el editor—, ni `SYSTEM`, `DETACH`, `ATTACH`, usuarios, roles,
  permisos, funciones o un `FORMAT` en un `SELECT`, porque la consola muestra
  directamente el resultado.
- **Detener** y el límite de tiempo finalizan una instrucción con `KILL QUERY`.
