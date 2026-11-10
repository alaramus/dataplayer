# Cassandra

Un clúster de Apache Cassandra o ScyllaDB, al que se llega por CQL. Exploras
sus keyspaces, lees tablas y vistas materializadas página a página, ves cómo
está hecha la clave de una tabla y lees su DDL tal como lo escribe el servidor.
Los dos productos son un mismo tipo de conexión: el catálogo de tipos muestra
una tarjeta para cada uno, y la conexión dice a cuál llegó.
La página [Conexiones](connections.md) explica cómo funcionan las conexiones
en general.

## Qué puedes ver

- Keyspaces, tablas y vistas materializadas
- Filas página a página, filtradas en el servidor, valores tal como se guardan
- Clave de partición, columnas de clustering e índices secundarios
- El DDL de una relación, tal como lo escribe el servidor
- Las tablas virtuales de Cassandra, como `system_views`
- Los resultados del CQL que escribes, en la consola o en cqlsh
- Nodos, clientes, tamaños de tablas, ajustes y roles del clúster
- Todas las filas que coinciden, descargadas en un archivo
- Clientes, solicitudes y tamaño del nodo, en un panel

## Qué puedes cambiar

- Datos: editar celdas, pegar bloques, insertar y eliminar filas
- Columnas e índices secundarios de una tabla
- Tablas nuevas, diseñadas con su clave de partición y de clustering
- Keyspaces: crearlos y eliminarlos; tablas: vaciarlas y eliminarlas
- Tablas copiadas con su estructura a otra conexión de Cassandra
- Datos y estructura, con CQL en la consola, un cambio cada vez

## Conexión

La página **Conexión** de la ventana pide:

- **Host** y **Puerto** del protocolo nativo, 9042 salvo que el servidor
  indique otro;
- **TLS**, con el certificado del servidor comprobado contra el host;
- **Autenticación**: un usuario y una contraseña, o nada para un servidor que
  no comprueba ninguna. Un Cassandra o un ScyllaDB nuevo suele tener
  `cassandra` con la contraseña `cassandra`;
- **Keyspace**: dónde se abre el catálogo. Puede quedar vacío;
- **Consistencia**: cuántas réplicas responden a una lectura y confirman una
  escritura. `LOCAL_ONE` salvo que elijas otra.

Una cadena de conexión como `cassandra://ann@db.example.com:9042/shop` pegada
en **URL** rellena estos campos; también se lee `scylla://`, `?ssl=true` activa
TLS y `?consistency=LOCAL_QUORUM` elige el nivel.

Cada sentencia va al nodo que indicas, aunque el clúster tenga otros: las
direcciones que los nodos dan de sí mismos a menudo no se alcanzan desde aquí —
detrás de Docker, un NAT o un túnel SSH — y el nodo indicado sí. Ese nodo pide
a los demás lo que no guarda.

Se admiten Cassandra 4.0 y ScyllaDB 5.4 y posteriores. Un servidor más antiguo
se rechaza al comprobar la conexión, indicando su versión.

## El catálogo

- El primer nivel son los keyspaces. El de la conexión va primero; `system` y
  los keyspaces `system_…` pertenecen al servidor y están marcados así, igual
  que `audit` de ScyllaDB.
- Dentro de un keyspace están sus tablas y vistas materializadas. ScyllaDB
  guarda un índice secundario en una vista oculta; no se lista, y el índice se
  muestra en su tabla.
- Las columnas de una tabla dicen cuáles forman la clave de partición, cuáles
  son columnas de clustering, en qué orden y cuáles son estáticas.

## Filas

- Las filas llegan en el orden del servidor, página a página. Ninguna columna
  se ordena: CQL ordena filas solo dentro de una partición nombrada entera.
- Un filtro sobre cualquier columna funciona. Sobre una columna fuera de la
  clave, hace que el servidor lea toda la tabla, lo que en una tabla grande
  puede agotar el tiempo.
- Los filtros comparan por igual, mayor, menor, al menos, como mucho y uno de
  una lista. ScyllaDB añade «empieza por» y «contiene» para texto; no se pueden
  buscar `%` ni `_`, porque su `LIKE` no tiene escape. Listas, conjuntos,
  mapas, tuplas, tipos definidos por el usuario, blobs, duraciones y
  contadores no se filtran.
- Los números llegan tal como se guardan, hasta la última cifra de un
  `varint` o un `decimal`. Una marca de tiempo se muestra en UTC. Listas,
  conjuntos, mapas, tuplas y tipos definidos por el usuario se muestran como
  JSON; un mapa cuyas claves no son texto, como una lista de pares. Un blob se
  muestra como `0x` y hexadecimal.
- Saltar muy adelante lee las filas intermedias, hasta cien mil. Más allá,
  avanza desde una página que ya hayas leído.
- La última página puede prometer más y resultar vacía: el servidor dice si
  podría haber más antes de mirarlo.

## Consola CQL

**Nueva consulta** en **Consultas**, en la barra izquierda, abre una sobre la
conexión, y **Abrir como consulta** encima de una tabla abre una sobre esa
tabla. Funciona como la consola de PostgreSQL — lecturas, cambios,
autocompletado — con estas diferencias:

- El lenguaje es CQL. El keyspace elegido encima del editor es el de los
  nombres sin calificar; un `USE` lo cambia solo para el resto de esa
  ejecución.
- No hay transacción. **Lectura** ejecuta solo sentencias que leen: `SELECT`,
  `DESCRIBE` y `LIST`. **Confirmación automática** ejecuta todo, pero una
  sentencia que cambia filas o estructura se ejecuta sola, porque Cassandra la
  guarda en el acto y no puede deshacerla. Los cambios que deben llegar juntos
  van en un solo `BEGIN BATCH … APPLY BATCH`, que cuenta como una sentencia.
- Los parámetros son los de CQL, `:name`. El servidor dice el tipo de cada uno
  y el valor se lee como ese tipo; una lista, un conjunto, un mapa, una tupla o
  un tipo definido por el usuario se escribe como JSON. **SQL null** envía null.
- `CONSISTENCY`, `TRACING`, `COPY`, `SOURCE`, `PAGING` y los demás comandos de
  cqlsh no son CQL y aquí se rechazan; ejecútalos en cqlsh.
- **Detener** deja de esperar la respuesta. Al servidor no se le puede pedir
  que detenga una sentencia, así que la termina igualmente.

## cqlsh

**Terminal** sobre una conexión abre cqlsh, con la sesión de la conexión, en el
keyspace que esta indica. También para ScyllaDB es el cqlsh de Cassandra;
ambos hablan CQL. Se ejecuta en un contenedor de este servidor, así que el host
debe ser alcanzable desde él, y una conexión por túnel SSH aún no tiene
terminal.

## Cambiar filas

- En una tabla se editan celdas, se pegan bloques y se insertan y eliminan
  filas. Las vistas materializadas, las tablas virtuales y los keyspaces del
  servidor son de solo lectura, igual que una tabla de contadores: un contador
  solo acepta una suma, que la consola sí puede escribir.
- Una fila se encuentra por su clave primaria. Las columnas de la clave no se
  editan — deciden dónde se guarda la fila — y una fila nueva necesita un valor
  para cada una.
- Una fila que alguien cambió después de que leyeras la página se rechaza en
  vez de sobrescribirse. Vuelve a leer la página y repite el cambio. Un cambio
  hecho en el mismo instante que el tuyo no se detecta: Cassandra no tiene una
  transacción que sujete la fila.
- Listas, conjuntos, mapas, tuplas y tipos definidos por el usuario se
  escriben como el JSON con que se muestran; una duración en las unidades de
  CQL, como `1mo2d3h`.
- Una columna estática guarda un valor para toda la partición, así que
  editarla en una fila la cambia en todas las filas de esa partición.
- Insertar una fila rechaza una clave que ya existe. Las filas pegadas o
  cargadas en bloque sustituyen a una fila con la misma clave, que es como
  escribe Cassandra.
- Un pegado se comprueba entero antes de escribir nada: un valor que su
  columna no admite, y nada cambia.

## Cambiar la estructura

- Las columnas de una tabla se añaden y se eliminan. Una columna de la clave
  primaria no se elimina; una que lee un índice o una vista materializada, el
  servidor tampoco deja eliminarla y dice por qué.
- Solo se puede renombrar una columna de la clave primaria: Cassandra no
  renombra nada más. Cassandra no tiene valores por defecto, columnas
  obligatorias fuera de la clave ni cambio de tipo, así que no se ofrecen.
- Un índice secundario se crea sobre una columna y se elimina. Cassandra 5
  ofrece el índice ligado al almacenamiento (SAI) y el clásico; ScyllaDB, su
  índice global. Ninguno es único.
- Las vistas materializadas, las tablas virtuales y los keyspaces del servidor
  no se cambian.

## Crear una tabla

- **Crear tabla** sobre un keyspace abre el diseñador de tablas. El plan es un
  `CREATE TABLE` y un `CREATE INDEX` por índice, mostrados antes de ejecutarse.
- La clave primaria es obligatoria. En la página de opciones de la tabla,
  **Clave de partición** nombra las primeras columnas de la clave primaria que
  deciden en qué nodo se guarda una fila; si se deja vacía, es la primera
  columna. El resto de la clave primaria ordena las filas dentro de una
  partición.
- El nombre de una tabla son letras, dígitos y guiones bajos; el de una columna
  puede ser cualquiera. Una columna puede ser una lista de su tipo, pero una
  lista y una duración no pueden estar en la clave.
- Claves únicas, claves foráneas, comprobaciones, valores por defecto,
  columnas calculadas, intercalaciones, particiones por rango, lista o hash y
  columnas obligatorias fuera de la clave no existen en CQL; el diseñador lo
  dice en el objeto que las pide.

## La sección «Clúster»

- Tras los keyspaces, **Clúster** contiene lo que el nodo dice del clúster:
  **Nodos**, **Clientes**, **Tamaños de tablas**, **Ajustes** y **Roles**. Se
  recorren como una tabla; Clientes se vuelve a leer cada pocos segundos. Los
  tamaños de tablas son la estimación del propio nodo.
- Los keyspaces `system` también están en el catálogo, para lo que estos
  informes no muestran.

## Buscar y descargar

- El campo de búsqueda encuentra keyspaces y tablas por nombre, y tablas por
  el nombre de una columna o por su comentario.
- La descarga toma todas las filas que coinciden con los filtros de una
  página, no solo la página.

## Acciones del catálogo

- **Nuevo keyspace** en lo alto de la conexión, guardado en el centro de datos
  del nodo con el número de réplicas que elijas.
- Sobre un keyspace: **Crear tabla** y **Eliminar keyspace**. Un keyspace solo
  se elimina cuando has visto lo que contiene y has marcado eliminarlo todo.
- Sobre una tabla: **Vaciar**, que elimina todas las filas y conserva la
  tabla, y **Eliminar**; sobre una vista materializada, **Eliminar**. Una tabla
  se elimina junto con las vistas materializadas que la leen, y la vista previa
  las nombra.
- Las tablas y los keyspaces no se pueden renombrar: CQL no tiene forma de
  hacerlo.

## Copiar tablas

**Copia** tablas en el catálogo y **pégalas** en un keyspace de otra conexión
de Cassandra o ScyllaDB, o de esta misma. Llegan con sus columnas, su clave de
partición y de clustering y su orden, su comentario, sus índices secundarios y
los tipos definidos por el usuario que usan; la ventana muestra cada sentencia
y no ejecuta nada antes de **Copiar**.

- Los tipos que le faltan al keyspace se crean primero, luego la tabla, luego
  sus filas y solo después sus índices.
- Una tabla de contadores no se copia: un contador no se escribe con `INSERT`.
  Las vistas materializadas no se copian; la que lee una tabla copiada se
  nombra en la ventana.
- Si la copia falla o se detiene, las tablas que creó se eliminan.
- Nada inmoviliza las tablas mientras se leen: las filas escritas entretanto
  pueden llegar o no.

Las filas pegadas en otro tipo de conexión siguen el camino de las filas de
cualquier tabla.

## Copias de seguridad

Todavía no se ofrecen para Cassandra y ScyllaDB.

## Paneles

Una conexión de Cassandra puede enviar datos a paneles. La disposición es
**Nodo de Cassandra**: clientes, tamaño y particiones del keyspace de la
conexión según la estimación del nodo, y en Cassandra solicitudes, lecturas,
escrituras y compactaciones por segundo y el trabajo en espera. ScyllaDB
guarda esos contadores en su propio punto de monitorización, que esta conexión
no lee.

## Un servidor propio

**Nueva conexión** ofrece **Iniciar Apache Cassandra aquí** en la tarjeta de
Cassandra e **Iniciar ScyllaDB aquí** en la de ScyllaDB: un nodo iniciado en
esta máquina, guardado como conexión con su superusuario `cassandra` y una
contraseña inventada para él. Un nodo de Cassandra tarda uno o dos minutos en
responder y fija su propia contraseña en cuanto responde. Con datos de ejemplo,
se abre en `demo_lab` — organizaciones y sus personas, proyectos y sus tareas,
veinte mil visitas a páginas en treinta días y una tabla de contadores de
visitas por página — con algo para cada pantalla: una columna estática, un
tipo definido por el usuario, colecciones, una duración, un índice secundario,
una vista materializada y un orden de clustering de lo más nuevo a lo más
antiguo.
