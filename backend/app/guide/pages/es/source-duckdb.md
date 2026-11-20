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

## Qué puedes cambiar

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

- Editar filas, cambiar la estructura, las acciones del catálogo, descargar
  todas las filas, las copias de seguridad y copiar tablas. Llegarán más
  adelante.
- Una tabla sin clave primaria seguirá siendo de solo lectura incluso
  entonces: DuckDB mueve una fila al actualizarla, y nada más la identifica.
- Un archivo en un servidor SSH, o dentro de otra conexión, no se puede abrir
  como base de datos.
