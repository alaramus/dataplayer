# Kafka

Un clúster de Kafka. Ves sus topics y grupos de consumidores, lees los mensajes
de un topic como filas y ves cuánto se retrasa cada grupo. Cómo funcionan las
conexiones en general se explica en la página [Conexiones](connections.md).

## Qué puedes ver

- Los topics, los grupos de consumidores y, aparte, los topics de Kafka
- Mensajes de un topic como filas, recientes primero, desde un momento u offset
- Los campos de los mensajes JSON, cada uno en su columna
- Cada partición de un topic: su líder, réplicas y offsets
- La configuración propia de un topic
- Dónde está cada grupo de consumidores en cada partición, y su retraso
- Informes del clúster: brokers, configuración, particiones que requieren atención
- Retraso, mensajes por segundo y estado del clúster en un panel
- Topics y grupos encontrados por nombre
- Los mensajes de un topic descargados en un archivo
- Las herramientas propias de Kafka, configuradas para la conexión, en un terminal

## Qué puedes cambiar

- Enviar mensajes, uno a uno o pegando filas
- Topics nuevos, con sus particiones y configuración
- Eliminar topics, cambiar su configuración, añadir particiones
- Eliminar los mensajes de un topic, todos o los anteriores a un momento
- Mover las posiciones de un grupo al principio, al final o a un momento
- Eliminar grupos de consumidores
- Todo lo que las herramientas de Kafka pueden cambiar, en el terminal

## Conexión

La página **Conexión** de la ventana pide:

- **Brokers**: `host:port` de uno o varios brokers, separados por comas. Basta
  con uno: le dice a DataPlayer dónde están los demás;
- **TLS**: una conexión cifrada, con los certificados de los brokers
  verificados;
- **Certificado de la CA**: la autoridad que los firmó, en PEM, cuando el
  sistema aún no confía en ella;
- **Autenticación**: **Ninguna**, o un usuario y contraseña con **SASL PLAIN**,
  **SASL SCRAM-SHA-256** o **SASL SCRAM-SHA-512**.

DataPlayer se conecta a las direcciones que los brokers anuncian de sí mismos,
así que deben ser accesibles desde el servidor de DataPlayer con esos nombres.
No se admite túnel SSH.

## El catálogo

- **Topics**, **Grupos de consumidores** y **Topics internos** — los propios
  de Kafka, como `__consumer_offsets`, cuyo nombre empieza por guion bajo.
- Un topic indica cuántas particiones tiene y cuántos mensajes abarcan. El
  número es un máximo: los topics compactados tienen huecos.
- Un grupo indica si está estable, reequilibrándose o sin consumidores, y
  cuántos consumidores tiene.
- Un nivel muestra los mil primeros por nombre.

## Los mensajes de un topic

- Una fila por mensaje: partición, offset, hora, clave, valor y cabeceras.
- Cuando los valores son objetos JSON, cada campo es también una columna,
  llamada `value.` más el campo. Los campos salen de los doscientos mensajes
  más recientes.
- Una clave o un valor que no es texto se muestra en hexadecimal.
- Los más recientes primero, en todas las particiones. Ordena por
  **timestamp** para empezar por los más antiguos; ninguna otra columna ordena.
- Filtrar por **partition**, **offset** o **timestamp** elige dónde empieza y
  termina la lectura: Kafka encuentra ese punto por sí mismo, por largo que sea
  el topic.
- Los filtros sobre la clave, el valor, las cabeceras y los campos recorren los
  mensajes leídos, hasta cien mil por página.
- Una página llega como mucho a diez mil mensajes desde el final. Para ir más
  atrás, filtra por hora o por partición y offset.
- Leer un topic no se une a ningún grupo ni mueve la posición de nadie.

## Enviar mensajes

- **+** sobre las filas de un topic añade un mensaje. Rellena lo que
  necesites: todo puede quedar vacío.
- **partition** vacía deja que Kafka elija por la clave; **timestamp** vacío es
  ahora.
- **key** y **value** son texto; `0x` seguido de dígitos hexadecimales se envía
  como esos bytes.
- Deja **value** vacío y rellena los campos `value.` para enviar un objeto
  JSON con ellos.
- **headers** es un objeto JSON de texto, como `{"source": "manual"}`.
- Las filas pegadas en un topic se envían como mensajes. Si un valor no se
  puede leer, no se envía nada y se indica la celda.
- En los topics propios de Kafka no se escribe desde aquí.

## Un grupo de consumidores

- Una fila por cada partición que lee el grupo: el topic, la partición, la
  posición confirmada por el grupo, el final de la partición y el retraso entre
  ambos, con el consumidor que la lee. Las filas se actualizan cada diez
  segundos.

## El panel de detalles

Selecciona un topic o un grupo y elige **Detalles** en el menú del catálogo.

- Un topic: su número de mensajes, una línea por partición con líder, réplicas,
  réplicas sincronizadas y offsets, y la configuración propia del topic.
- Un grupo: su estado, consumidores, retraso total, broker coordinador,
  estrategia de asignación y topics.

## Las herramientas de Kafka

**Terminal** en una conexión Kafka abre las herramientas de línea de comandos
de Kafka, las que usa su documentación, ya apuntadas a la conexión: sus
brokers, su TLS y su usuario. Escribe una herramienta sin
`--bootstrap-server`:

- `kafka-topics.sh --list` — los topics
- `kafka-console-consumer.sh --topic NAME --from-beginning` — leer un topic;
  Ctrl+C lo detiene
- `kafka-consumer-groups.sh --describe --all-groups` — el retraso de cada grupo

Indica tú `--bootstrap-server` para apuntar una herramienta a otro clúster. El
terminal se ejecuta en un contenedor en el servidor de DataPlayer, así que ese
servidor debe poder iniciar contenedores y los brokers deben ser accesibles
desde él.

## Cambiar topics y grupos

Marca un topic en el nivel **Topics** y abre el menú del catálogo:

- **Nuevo topic** — un nombre, el número de particiones, un factor de
  replicación (vacío para el valor predeterminado del broker) y la
  configuración, un `name=value` por línea.
- **Eliminar topic** — la ventana indica cuántos mensajes se van y qué grupos
  leen el topic.
- **Cambiar la configuración** — se abre con la configuración propia del topic;
  quita una línea para devolver ese ajuste al valor predeterminado del broker.
- **Añadir particiones** — solo se pueden añadir, nunca quitar. Desde entonces
  una clave puede ir a otra partición.
- **Eliminar mensajes** — todos, o los anteriores a un momento. No se puede
  deshacer.

Marca un grupo en el nivel **Grupos de consumidores** para **Mover
posiciones**: al principio, al final o a un momento, para todos sus topics o
uno. Las posiciones solo se mueven mientras no se ejecuta ninguno de sus
consumidores. La ventana muestra cada partición antes y después. **Eliminar
grupo** quita un grupo y sus posiciones, también solo mientras nadie lee en él.

## La sección Clúster

Arriba del catálogo, **Clúster** reúne lo que el clúster dice de sí mismo:
**Clúster** (su id, el controlador y cuántos brokers, topics y particiones),
**Brokers**, **Configuración del broker** (la que difiere de los valores
predeterminados de Kafka) y **Particiones que requieren atención** (vacío si
todo va bien). El primero y el último se actualizan cada diez segundos.

## Paneles, búsqueda y descargas

- El panel **Clúster de Kafka** dibuja el retraso de cada grupo, los mensajes
  por segundo de cada topic y las particiones que requieren atención, para los
  cien primeros topics y grupos por nombre.
- La búsqueda de la cabecera encuentra topics y grupos por nombre.
- **Descargar** en un topic guarda los mensajes que mostraría su página, con
  sus filtros y su orden, hasta diez mil desde el final de cada partición. Un
  grupo descarga todas sus posiciones.

## Un topic en un pipeline

Un topic puede estar en medio de un pipeline: un enlace escribe en él y otros
llevan lo que llega a tablas.

- **Añadir filas** a un topic envía las filas como mensajes.
- **Añadir los mensajes nuevos a una tabla** solo lee lo que llegó desde la
  última ejecución de ese enlace. Es la única salida de un topic en un
  pipeline: leer todo el topic en cada ejecución volvería a añadir las mismas
  filas.
- Cada enlace así lee como un grupo de consumidores propio, llamado
  `dataplayer-link-` y el id del enlace, que se muestra en el panel del
  enlace. Su retraso aparece en el nivel **Grupos de consumidores**.
- **La primera ejecución lee** elige dónde empieza la primera ejecución:
  desde el principio del topic o solo los mensajes que lleguen después. Cuando
  el grupo ya guarda una posición, la elección no cambia nada; para volver a
  leer, mueva las posiciones del grupo.
- Cada bloque de filas se escribe primero y su posición se guarda después. Si
  una ejecución falla entre ambos pasos, la siguiente vuelve a escribir ese
  bloque: ningún mensaje se pierde, y rara vez llega dos veces.
- **Añadir los mensajes nuevos a una tabla nueva**, trazado hacia un esquema en
  lugar de una tabla, crea la tabla en la primera ejecución — nombre, columnas
  y tipos elegidos en su ventana — y después añade a ella. Si entre sus
  columnas están partition y offset del topic, se crea con una clave sobre
  ellas donde la base lo permite (PostgreSQL, MySQL, MariaDB, SQLite), y un
  mensaje escrito dos veces se guarda una sola. Una tabla eliminada después no
  se vuelve a crear: mueva las posiciones del grupo al principio para leerlo
  todo en una nueva.
- Los mensajes que Kafka borró antes de que el enlace los leyera se cuentan en
  el resultado de la ejecución.
- Kafka olvida las posiciones de un grupo tras una semana sin escribirlas; un
  enlace que se ejecuta con menos frecuencia empieza de nuevo como dice **La
  primera ejecución lee**.

## Un Kafka propio

**Servicios** puede iniciar un broker de Kafka en esta máquina, si este
servidor puede ejecutar contenedores. No pide contraseña — un broker responde a
quien lo alcanza — y solo es accesible desde esta máquina. Su conexión se crea
por ti.

Pide datos de ejemplo para tener un laboratorio:

- `lab.orders` — trescientos pedidos JSON de un día en tres particiones, con
  el cliente como clave;
- `lab.prices` — el último precio por símbolo, un topic compactado;
- `lab.events` — líneas de texto con cabeceras;
- `lab.sensor` — lecturas guardadas como bytes, mostradas en hexadecimal;
- el grupo `lab-billing`, a mitad de `lab.orders`, para que se vea su retraso.

Un broker dice a sus clientes dónde está, y este da la dirección que tiene
dentro de DataPlayer. El catálogo, el terminal y los pipelines lo alcanzan
ahí; una herramienta en tu propio equipo, solo a través del terminal.

## Lo que Kafka aún no tiene aquí

No se ofrece copiar topics a otra conexión ni copias de seguridad. Kafka copia
con MirrorMaker, un servicio que sigue en marcha, y su copia de seguridad son
los archivos de registro de los brokers; volver a enviar cada mensaje no daría
ni lo uno ni lo otro.
