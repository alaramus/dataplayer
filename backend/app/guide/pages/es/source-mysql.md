# MySQL

Un servidor MySQL o MariaDB. Recorres sus bases de datos, lees tablas y vistas
página a página, ves cómo está construida una tabla, lees su DDL tal como lo
escribe el servidor y ejecutas SQL en una consola. Cómo funcionan las conexiones
en general se explica en la página [Conexiones](connections.md).

## Qué puedes ver

- Bases de datos, tablas y vistas, y sus filas ordenadas y filtradas en el
  servidor
- Las columnas, claves, comprobaciones e índices de una tabla, y las tablas a
  las que hace referencia
- Adónde lleva la clave externa de una fila, y qué apunta a ella
- El DDL de una relación, tal como lo escribe el servidor
- Cuánto ocupa una tabla, y cuándo se creó y se escribió en ella por última vez
- Los resultados del SQL que escribes, y el plan del servidor para una consulta
- Todas las filas coincidentes, descargadas como archivo
- Lo que hace el servidor: procesos, variables, estado, usuarios, rutinas,
  disparadores, eventos y motores

## Qué puedes cambiar

- Los datos de una tabla: editar celdas, pegar bloques, insertar y eliminar
  filas
- Columnas, índices, claves únicas y claves externas
- Tablas nuevas, diseñadas objeto por objeto o hechas a partir de filas
- Datos y estructura, con SQL en la consola
- Lo que ejecuta otra conexión: su sentencia se puede detener, o cerrar la
  conexión
- Bases de datos: crearlas y eliminarlas
- Tablas y vistas: renombrar, mover una tabla a otra base de datos, eliminar
- Tablas copiadas con su estructura a otra conexión MySQL o MariaDB
- Copias de seguridad de la base de datos de la conexión, y la base restaurada
  desde una de ellas

## Conectarse

La página **Conexión** de la ventana pide:

- **Host** y **Puerto**, 3306 salvo que el servidor diga otra cosa;
- **Autenticación**: un usuario y una contraseña, o un usuario sin contraseña;
- **Base de datos**: donde se abre el catálogo. Puede quedar vacía. Toda base
  de datos que el usuario pueda ver está en el catálogo de todos modos.

Una cadena de conexión como `mysql://ann@db.example.com:3306/sales` pegada en
**URL** rellena estos campos; `mariadb://` se lee igual. Una contraseña en la
cadena pegada pasa al campo de la contraseña y sale de la cadena.

La conexión se cifra cuando el servidor ofrece TLS, y queda sin cifrar cuando
no. El certificado del servidor no se comprueba.

Se admiten MySQL 8.0.16 y posteriores y MariaDB 10.6 y posteriores. Un servidor
más antiguo se rechaza al comprobar la conexión, indicando su versión.

## El catálogo

- El primer nivel son las bases de datos. La que nombra la conexión va primero;
  `mysql`, `information_schema`, `performance_schema` y `sys` pertenecen al
  servidor y están marcadas como tales.
- Dentro de una base de datos están sus tablas y vistas. Pulsar una abre sus
  filas en una pestaña.
- Una tabla indica aproximadamente cuántas filas tiene. El número es la
  estimación del servidor, que MySQL puede conservar hasta un día, y nada cuenta
  las filas.
- **Detalles** indica cuántas columnas, índices y restricciones tiene una
  relación, cuánto ocupa, y cuándo se creó y se escribió en ella por última vez.
- **Mostrar DDL** muestra la sentencia `CREATE TABLE` o `CREATE VIEW` que da el
  propio servidor.
- **Sistema**, después de las bases de datos, es una sección de informes que el
  servidor da sobre sí mismo (consulta **Informes** más abajo).
- La búsqueda de la cabecera encuentra bases de datos y tablas por su nombre, y
  tablas por sus columnas y por los comentarios sobre ellas y sus columnas.

## Leer filas

Una tabla se abre como una cuadrícula, página a página, ordenada y filtrada por
el servidor como una tabla de PostgreSQL. Lo que ofrece una columna depende de
su tipo: comparaciones para números, fechas y texto; «contiene» y «empieza por»
para texto; igualdad y «uno de una lista» para enumeraciones; vacío o no vacío
para cualquier columna.

- Las páginas siguen la clave primaria. Una tabla sin ella sigue una clave
  única sobre columnas que no pueden estar vacías, el orden en que InnoDB guarda
  una tabla así. Una tabla sin ninguna de las dos, y una vista, siguen el orden
  que devuelve el servidor.
- Un `%` o un `_` escrito en un filtro de texto se busca tal cual.
- **Descargar** pregunta por **Página actual** o **Todas las filas
  coincidentes**. Cada fila se lee del servidor a medida que se escribe en el
  archivo, en el orden de la página y con sus filtros.

Cómo se muestran los valores:

- `DECIMAL` y los enteros grandes sin signo exactamente como se guardan;
- `BIT` como un número;
- `TIMESTAMP` en UTC, con `+00:00`. `DATETIME` tal como se escribió, sin zona
  horaria, porque no la tiene;
- `TIME` tal como lo escribe MySQL, que puede ser negativo o superar las 24
  horas;
- una fecha cero como `0000-00-00` tal como la escribe el servidor;
- la geometría como texto, por ejemplo `POINT(1 2)`;
- las columnas binarias en hexadecimal, por ejemplo `0x00FF`.

## Cambiar filas

Con el acceso **Editar filas**, una tabla se edita en su cuadrícula como una
tabla de PostgreSQL: doble clic en una celda, pegar un bloque, **Insertar
fila**, marcar filas y **Eliminar las filas seleccionadas**.

- Una fila se vuelve a encontrar por su clave primaria, o por una clave única
  sobre columnas que no pueden estar vacías. Una fila de una tabla sin ninguna
  de las dos se encuentra por todos sus valores, y se cambia una fila cada vez:
  las filas iguales en cada valor son intercambiables. Dos filas que solo se
  diferencian en una columna de coma flotante, JSON o geometría no se pueden
  distinguir, y un cambio en una de ellas se rechaza por ese motivo.
- Si alguien cambió una fila después de que la leyeras, en cualquier columna, tu
  cambio se rechaza en lugar de escribirse encima del suyo. Vuelve a cargar e
  inténtalo de nuevo.
- Un valor que la columna no puede contener se rechaza antes de escribir nada,
  y se nombran las celdas que contienen esos valores. Nada de un bloque pegado
  llega hasta que todo puede llegar.
- Escribe los valores como los muestra la cuadrícula: binario como `0x…`,
  geometría como WKT, por ejemplo `POINT(1 2)`, un `TIMESTAMP` con su
  desplazamiento.
- Una celda de una clave externa tiene una flecha que abre la fila a la que
  apunta, y **Qué apunta a esta fila** abre las filas que apuntan aquí, en esta
  base de datos o en otra del servidor.

## Cambiar la estructura

**Estructura** de una tabla la cambia como a una tabla de PostgreSQL: añadir,
renombrar y eliminar una columna, fijar o quitar su valor predeterminado, exigir
un valor o dejar de exigirlo, cambiar su tipo, añadir y eliminar índices, claves
únicas y claves externas.

- Todo lo demás de una columna —su valor predeterminado, comentario, juego de
  caracteres, AUTO_INCREMENT— se conserva cuando cambia su tipo o si admite
  nulos.
- Un cambio que las filas ya contradicen no se hace, y se muestra el recuento:
  filas sin valor, valores que se repiten, filas que apuntan a nada, valores que
  el nuevo tipo no puede contener. MySQL solo puede contar estos últimos después
  de intentar el cambio y ser rechazado; no se cambia nada en ningún caso.
- Los tipos ofrecidos son los de MySQL: texto, texto largo, entero, entero
  grande, decimal, coma flotante, booleano como 0 o 1, fecha, fecha y hora,
  marca de tiempo, JSON, y un UUID como texto.
- Los índices son de árbol B, de texto completo (solo columnas de texto) o
  espaciales (una columna de geometría que exige un valor). MySQL pone nombre él
  mismo a un índice o una clave nuevos.
- Una clave única y su índice son una sola cosa en MySQL; elimínala como clave.
- `SET DEFAULT` no se ofrece para una clave externa: InnoDB no lo ejecuta.

## Crear una tabla

**Crear tabla** en el menú de acciones de una base de datos abre el diseñador
de tablas, como en PostgreSQL. El plan es un único `CREATE TABLE` con cada
clave, comprobación, clave externa e índice dentro, de modo que la tabla se crea
entera o no se crea.

- Lo que MySQL no tiene se marca en el objeto que lo pide antes de que puedas
  revisar el plan: una clave diferible, columnas adicionales llevadas por un
  índice, un índice sobre parte de las filas, nulos ordenados primero o al
  final, una tabla sin registro o particionada.
- Una columna de identidad es AUTO_INCREMENT: una por tabla, al principio de una
  clave, con un valor inicial pero sin incremento propio.
- Una clave primaria siempre se llama PRIMARY.
- Las filas guardadas como tabla, o un archivo cargado en una, se comprueban con
  los tipos elegidos antes de crear la tabla; si aun así se rechazan, la tabla
  nueva se vuelve a quitar.

## Consola SQL

**Nueva consulta** en **Consultas** de la barra izquierda inicia una en la
conexión, y **Abrir como consulta** sobre una tabla inicia una sobre esa tabla.
Funciona como la consola de PostgreSQL —lecturas, cambios confirmados al
instante o mantenidos en una transacción **Manual**, **Explicar**, autocompletado
y formato— con estas diferencias:

- La base de datos elegida sobre el editor es la predeterminada, como la dejaría
  `USE`; una base de datos cada vez.
- Los parámetros se escriben `:name`. Cada valor se envía como texto, así que un
  número que el servidor necesita como número, por ejemplo después de `LIMIT`,
  no puede ser un parámetro.
- Un cambio de estructura —`CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `RENAME`— se
  ejecuta solo. MySQL lo confirma al instante, junto con todo lo anterior, así
  que no puede compartir una ejecución con otras sentencias, ni ejecutarse
  dentro de una transacción que mantienes, ni probarse antes. La consola
  pregunta antes de ejecutar uno, y lo dice.
- Una sentencia que falla dentro de una transacción que mantienes deja la
  transacción abierta; un interbloqueo la termina.
- **Detener** y el límite de tiempo terminan una sentencia con `KILL QUERY`.
- Los usuarios, permisos, rutinas, disparadores y eventos no se cambian desde la
  consola. `LOAD DATA`, `SELECT … INTO OUTFILE` y `CALL` no se ejecutan.

## Informes

**Sistema** en el catálogo contiene ocho informes sobre el servidor. Se leen
como tablas, y se pueden ordenar, filtrar, descargar y representar en gráficos.
**Mostrar la instrucción** muestra el SQL que ejecuta un informe.

- **Procesos**: las conexiones abiertas ahora y lo que ejecuta cada una. Cada
  fila tiene **Cancelar consulta**, que detiene la sentencia y mantiene la
  conexión, y **Finalizar**, que cierra la conexión. El informe se vuelve a leer
  solo cada cinco segundos.
- **Variables**: cada ajuste global del servidor.
- **Estado**: los contadores que el servidor lleva desde que arrancó. Se vuelve
  a leer solo cada diez segundos.
- **Usuarios**: las cuentas que pueden conectarse, y desde qué hosts. **Nuevo
  usuario** sobre las filas crea una: un nombre, el host desde el que puede
  conectarse (`%` para cualquier lugar) y una contraseña. No se le concede nada
  o, si se marca, la lectura de la base de datos de la conexión. Solo el
  propietario de la conexión tiene este comando.
- **Rutinas** y **Disparadores** fuera de las bases de datos propias del
  servidor, y los **Eventos** que ejecuta su planificador.
- **Motores**: los motores de almacenamiento que ofrece el servidor, y cuál es
  el predeterminado.

Un informe muestra solo lo que puede ver el usuario de la conexión: un usuario
sin el privilegio `PROCESS` solo ve sus propias conexiones, y **Usuarios** se
rechaza a quien no puede leer la base de datos `mysql`.

## Acciones del catálogo

- **Nueva base de datos**, en el nivel superior del catálogo.
- **Eliminar base de datos** pregunta primero. Una base de datos que contiene
  algo solo se elimina con **Eliminar también todo su contenido** marcado, y lo
  que contiene se cuenta antes de que confirmes.
- **Renombrar** una tabla o una vista. Las claves externas que apuntan a una
  tabla la siguen.
- **Mover a una base de datos** mueve una tabla. Una vista, y una tabla con
  disparadores, se quedan en su base de datos.
- **Eliminar** una relación o varias juntas. Una tabla a la que hace referencia
  una tabla fuera de la selección no se elimina, y se nombran las tablas que le
  hacen referencia. En MySQL también se nombran las vistas que leen una tabla
  eliminada.
- **Cargar desde CSV** hace una tabla a partir de un archivo, con cada columna
  como `TEXT`.
- **Modelo como código** escribe una base de datos o una selección para un ORM o
  un diagrama.

Los cambios de estructura no se ensayan primero, como en PostgreSQL: MySQL los
confirma al instante.

## Copiar tablas

**Copia** tablas en el catálogo y **pégalas** en una base de datos de otra
conexión MySQL o MariaDB, o de esta. Llegan con sus columnas, claves, índices,
comprobaciones y opciones; la ventana pregunta lo mismo que en PostgreSQL,
muestra cada sentencia y no ejecuta nada antes de **Copiar**.

- Los disparadores se quedan atrás, nombrados en la ventana. Las vistas y las
  tablas particionadas no se copian así.
- Primero se crean las tablas y después llegan las filas. Si la copia falla o se
  detiene, las tablas que creó se vuelven a eliminar.
- MariaDB usa una intercalación que MySQL no tiene, así que una tabla copiada de
  MariaDB a MySQL puede rechazarse; la ventana dice qué paso la rechazó.

Las filas pegadas en una conexión de otro tipo siguen el camino de las filas de
cualquier tabla.

## Copias de seguridad

**Copias de seguridad**, en el menú de acciones del catálogo, funciona como en
PostgreSQL, para la base de datos que nombra la conexión. A una conexión que no
nombra ninguna base de datos no se le ofrece.

- La copia es un archivo SQL escrito por `mysqldump`, o por `mariadb-dump` para
  MariaDB, de la versión del propio servidor, con rutinas, disparadores y
  eventos.
- **Restaurar** elimina y vuelve a crear cada tabla, vista y rutina que contiene
  la copia. Una copia hecha desde MariaDB solo se restaura en MariaDB, y una
  hecha desde MySQL solo en MySQL.

## Cuadros de mando

Una conexión MySQL puede informar a los cuadros de mando. El diseño se llama
**Servidor MySQL**: conexiones, sentencias, filas, lecturas del búfer, tráfico
de red, consultas lentas y conexiones interrumpidas, y el tamaño de la base de
datos de la conexión. Los contadores son de todo el servidor: MySQL no los
lleva por base de datos.

## Un servidor propio

**Nueva conexión** ofrece **Iniciar MySQL aquí** e **Iniciar MariaDB aquí**: un
servidor iniciado en esta máquina, guardado como una conexión que entra como su
root. Con datos de ejemplo, se abre en `demo_lab` —organizaciones, personas,
proyectos, unos cientos de tareas y mediciones— con algo para cada pantalla:
columnas generadas, JSON, una tabla particionada, claves de texto completo y
espaciales, una vista, un disparador y una tabla sin clave.

## Lo que MySQL aún no tiene aquí

- Una base de datos no se puede renombrar; MySQL no tiene forma de hacerlo.
