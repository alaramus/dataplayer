# DuckDB

Un archivo de base de datos DuckDB en tu almacenamiento personal. Exploras sus
esquemas, tablas y vistas, lees sus filas página a página, ves cómo está hecha
una tabla y lees el DDL que el archivo guarda para ella.
Cómo funcionan las conexiones en general está en la página
[Conexiones](connections.md).

## Qué puedes ver

- Esquemas, tablas y vistas, y sus filas ordenadas y filtradas
- Columnas, claves, comprobaciones e índices de una tabla, y las tablas que cita
- El DDL de una relación, como lo guarda el archivo, con sus índices
- Listas, structs y maps, mostrados como JSON
- Los resultados del SQL que escribes y el plan de DuckDB
- Informes: tamaño del archivo, secuencias, tipos, macros y funciones
- Todas las filas de una tabla, una vista o un informe, descargadas

## Qué puedes cambiar

- Datos de tablas: editar celdas, pegar bloques, insertar y borrar filas
- Columnas, índices y claves únicas
- Tablas nuevas, diseñadas objeto por objeto o creadas a partir de filas
- Esquemas creados y eliminados; tablas y vistas renombradas y eliminadas
- Datos y estructura, mediante SQL en la consola

## Conectarse

La página **Conexión** de la ventana pide:

- **Archivo de base de datos**: la ruta del archivo dentro de tu
  almacenamiento personal, como `data/shop.duckdb`. Pon antes el archivo ahí
  mediante una conexión **Archivos**. Una ruta fuera de tu almacenamiento se
  rechaza.
- **Crear el archivo si no existe**: márcalo para empezar con una base vacía.
  Sin ello, un archivo que no está falla la comprobación, y una ruta mal
  escrita no deja un archivo vacío. La carpeta ya debe existir.

El archivo se abre de nuevo en cada petición y se cierra después, así que
entre peticiones tu propio DuckDB, un notebook o un script también pueden
abrirlo. Mientras otro programa lo tiene abierto, esta conexión dice que el
archivo está en uso.

Un archivo escrito por un DuckDB más nuevo que el de este servidor puede no
abrirse, y un archivo escrito por este servidor, un DuckDB 2, puede no abrirse
en DuckDB 1.

Lo que una conexión al archivo no puede hacer, contenga lo que contenga: leer
un archivo fuera de tu almacenamiento personal, salir a la red, instalar o
cargar una extensión, ni volcar a disco una ordenación grande. Una vista del
archivo que lee un archivo de otro sitio se rechaza al abrirla. Los archivos
de tu almacenamiento se nombran desde su raíz con `~/`, como
`~/data/sales.parquet`.

## El catálogo

- El primer nivel son los esquemas del archivo, `main` entre ellos.
- Dentro de cada uno están sus tablas y vistas. Al pulsar una se abren sus
  filas en una pestaña.
- Una tabla dice aproximadamente cuántas filas tiene, según estima DuckDB sin
  contar.
- **Detalles** dice cuántas columnas, índices y restricciones tiene una
  relación.
- **Ver DDL** muestra la sentencia `CREATE TABLE` o `CREATE VIEW` que guarda el
  archivo, seguida de los índices de la tabla.
- DuckDB nombra las restricciones por sí mismo, como `items_id_pkey`, aunque la
  sentencia les diera un nombre.

## Leer filas

Una tabla se abre como cuadrícula, una página cada vez, ordenada y filtrada
como una tabla de PostgreSQL. Lo que ofrece una columna depende de su tipo:
comparaciones para números, fechas y texto; igual o distinto para UUID, enums
e intervalos; contiene y empieza por para texto, JSON, listas y structs; vacío
o no vacío para cualquier columna.

- Las páginas siguen la clave primaria, o si no el orden en que DuckDB guarda
  las filas. Una vista va en el orden que devuelve DuckDB.
- Una lista, un struct o un map no se pueden ordenar.
- DuckDB lee un valor de filtro como el tipo de la columna: una fecha como
  `2026-01-02`, un instante con su zona horaria, un decimal hasta su última
  cifra. Un valor que DuckDB no puede leer así se rechaza.
- Un `%` o un `_` escrito en un filtro de texto se busca tal cual. Los filtros
  de texto no distinguen mayúsculas.

Cómo se muestran los valores, como los escribe DuckDB:

- enteros grandes y decimales con exactitud;
- un instante con zona horaria en UTC;
- los valores binarios en hexadecimal, como `0xAA00`;
- un intervalo como `1 year 2 days 03:00:00`;
- una lista, un struct, un map o una union como JSON.

## Cambiar filas

Con acceso **Editar filas**, una tabla se edita en su cuadrícula como una
tabla de PostgreSQL: doble clic en una celda, pegar un bloque, **Insertar
fila**, marcar filas y **Eliminar las filas seleccionadas**.

- Una fila se vuelve a encontrar por su clave primaria. Una tabla sin clave
  acepta filas nuevas y por lo demás es de solo lectura, porque DuckDB mueve
  una fila al actualizarla y puede guardar dos filas idénticas. Una vista es de
  solo lectura.
- Si alguien cambió una fila después de que la leyeras, tu cambio se rechaza en
  vez de sobrescribir el suyo. Recarga y vuelve a intentarlo.
- Escribe los valores como los muestra la cuadrícula: una fecha como
  `2026-01-02`, un instante con su zona horaria, binario como `0x…`. DuckDB los
  lee según el tipo de la columna, y un valor que no puede leer se rechaza; en
  un bloque pegado se nombran las celdas rechazadas y no se escribe nada.
- Las listas, structs, maps y columnas generadas no se editan en la cuadrícula;
  cámbialas con SQL en la consola.
- Un cambio que rechazan las claves, comprobaciones o columnas obligatorias de
  la tabla no se hace, y se dice qué regla lo rechazó.
- DuckDB no puede cambiar una clave ni una columna única de una fila a la que
  hacen referencia otras filas, ni siquiera a un valor que nadie tiene; las
  demás columnas de esa fila sí cambian.
- Una celda de una clave foránea tiene una flecha que abre la fila a la que
  apunta, y **Qué apunta a esta fila** abre las filas que apuntan aquí.

## Cambiar la estructura

**Estructura** de una tabla la cambia como cambia una tabla de PostgreSQL:
añadir, renombrar y eliminar una columna, fijar o quitar su valor por defecto,
exigir un valor o dejar de exigirlo, cambiar su tipo, añadir y eliminar
índices, añadir una clave única.

- DuckDB hace cada cambio en el sitio, en una transacción; no se reconstruye
  nada.
- Un cambio que las filas ya contradicen no se hace, y se muestra el recuento:
  filas sin valor, valores que no se convertirían al nuevo tipo, valores que se
  repiten.
- Un valor por defecto se comprueba con el tipo de la columna antes de fijarlo.
- DuckDB no puede añadir una clave foránea ni una comprobación a una tabla que
  ya existe, ni eliminar ninguna de sus restricciones, tampoco la clave
  primaria. En su lugar, copia la tabla en otra diseñada como quieras.
- Una tabla con un índice propio, o a la que apunta la clave foránea de otra
  tabla, solo admite una columna nueva, un valor por defecto y un índice nuevo.
  Renombrar, eliminar o cambiar el tipo de una columna, exigir un valor y
  añadir una clave única se rechazan.
- DuckDB renombra y elimina una columna sin mirar las vistas que la leen, así
  que tras el cambio se vuelve a leer cada vista, y una que el cambio rompería
  lo rechaza por su nombre.
- Lo que DuckDB rechaza por sí mismo, como eliminar una columna que cubre un
  índice, se dice con las palabras de DuckDB.
- Los tipos ofrecidos son los de DuckDB: texto, enteros de cuatro tamaños, coma
  flotante, decimal, booleano, fecha, hora, fecha y hora con o sin zona
  horaria, intervalo, UUID, JSON y binario.
- DuckDB construye un solo tipo de índice, un árbol radix adaptativo, con el
  nombre de la tabla y sus columnas. Las restricciones las nombra el propio
  DuckDB.

## Crear una tabla

**Crear tabla** en el menú de acciones de un esquema abre el diseñador de
tablas, como en PostgreSQL. El plan es un `CREATE TABLE`, un `CREATE INDEX` por
índice y los comentarios, ejecutados juntos: la tabla se crea entera o no se
crea.

- Una columna de identidad es una secuencia propia, `<tabla>_<columna>_seq`,
  creada antes que la tabla, y el valor por defecto de la columna toma su
  siguiente valor. Puede empezar en cualquier número y avanzar de cualquier
  paso. Acepta un valor que escribas en ella, por lo que no puede ser ALWAYS.
- Una columna generada se calcula cada vez que se lee; una que se pide
  almacenada se crea así, con un aviso.
- Lo que DuckDB no tiene se marca en el objeto que lo pide antes de que puedas
  revisar el plan: una tabla sin registro o particionada, una clave foránea en
  cascada, que pone nulo o un valor por defecto, o que apunta a otro esquema,
  una clave comprobada al confirmar, un índice sobre parte de las filas o con
  columnas adicionales.
- Un valor por defecto se comprueba con el tipo de su columna mientras se hace
  el plan.
- Los nombres de restricciones que des no se conservan; DuckDB nombra las
  restricciones por sí mismo.
- Los comentarios de la tabla y sus columnas se conservan.
- Las intercalaciones son las propias de DuckDB: `NOCASE`, `NOACCENT` y `NFC`.
- Las filas guardadas como tabla, o un archivo cargado en una, llegan con la
  tabla de una vez. Un valor que DuckDB no puede leer como el tipo de su
  columna deja la tabla sin crear.

## Informes

**Sistema** en el catálogo contiene cinco informes. Se leen como tablas y se
pueden ordenar, filtrar, descargar y representar en gráficos. **Mostrar la
instrucción** muestra el SQL que ejecuta un informe.

- **Base de datos**: la versión de DuckDB, el tamaño del archivo, sus bloques
  usados y libres, y el registro de escritura anticipada.
- **Secuencias**, con su inicio, su paso y sus límites. Una identidad creada
  por el diseñador de tablas es una de ellas.
- **Tipos** propios del archivo: enums, structs y otros nombres para un tipo.
- **Macros**: funciones escritas en SQL y guardadas en el archivo, con sus
  parámetros y su cuerpo.
- **Funciones** integradas en DuckDB, y cuántas firmas tiene cada una.
- La configuración del motor no se muestra: nombra carpetas del servidor y aquí
  es fija.

## Acciones del catálogo

- **Nuevo esquema** en la parte superior de la conexión. **Eliminar esquema**
  elimina cualquier esquema salvo `main`; uno que contiene algo necesita
  **Eliminar también todo su contenido**, y la pregunta cuenta lo que se va. En
  DuckDB un esquema no se puede renombrar.
- **Renombrar** una tabla o una vista. Después se vuelve a leer cada vista, y
  una que leía el nombre antiguo rechaza el cambio y se nombra. DuckDB no
  renombra una tabla con un índice propio ni una a la que apunta la clave de
  otra tabla.
- Una tabla con clave foránea propia no se renombra: DuckDB conservaría el
  nombre antiguo en la tabla a la que apunta, que ya no podría borrar sus filas
  ni ser eliminada.
- **Eliminar** una relación o varias juntas. La eliminación se prueba primero y
  se deshace, así que la pregunta nombra las vistas que dejarían de funcionar.
  Una tabla a la que apunta la clave de otra se rechaza salvo que esa otra se
  elimine con ella. Una secuencia de la que solo toman valores las tablas
  eliminadas, como la de una identidad, se elimina con ellas.
- **Cargar desde CSV** crea en el esquema una tabla a partir de un archivo,
  cada columna como `VARCHAR`.
- **Modelo como código** escribe un esquema o una selección para un ORM o un
  diagrama.
- Nada se mueve entre esquemas: DuckDB no puede.

## Consola SQL

**Nueva consulta** en **Consultas** de la barra izquierda inicia una en la
conexión, y **Abrir como consulta** sobre una tabla inicia una en esa tabla.
Funciona como la consola de PostgreSQL — lecturas, cambios confirmados en el
acto o retenidos en una transacción **Manual**, **Explicar**, autocompletado y
formato. DuckDB cambia la estructura dentro de una transacción, así que un
`CREATE`, `ALTER` o `DROP` forma parte de la transacción que lo rodea, y un
borrado se prueba primero y se deshace antes de que la consola te pregunte.

- Los archivos de tu almacenamiento se leen como `~/…`, por ejemplo
  `SELECT * FROM '~/data/sales.parquet'`. Carga uno en una tabla con
  `INSERT INTO t SELECT * FROM '~/data/sales.csv'`.
- Los parámetros se escriben `$name`.
- El esquema se elige encima del editor; `USE` y `SET` no se ejecutan.
- No se ejecutan, cada uno con su motivo: `ATTACH`, `COPY`, `EXPORT` e
  `IMPORT DATABASE`, `INSTALL` y `LOAD`, `PREPARE` y los secretos.
- Una sentencia que falla dentro de una transacción retenida la termina: solo
  queda **Revertir**.
- Mientras retienes una transacción, el archivo sigue abierto y ningún otro
  programa puede abrirlo.
- Dentro de una transacción retenida un borrado no se puede probar primero,
  porque DuckDB no tiene puntos de guardado; ejecútalo en confirmación
  automática.
- **Explicar** muestra el plan de DuckDB: sus operadores y las filas que
  espera.
- **Detener** y el límite de tiempo terminan una sentencia donde esté.

## Lo que DuckDB aún no tiene aquí

- Copiar tablas y las copias de seguridad. Llegarán más adelante.
- Un archivo en un servidor SSH, o dentro de otra conexión, no se puede abrir
  como base de datos.
