# RabbitMQ

Un broker de RabbitMQ. Ves sus hosts virtuales, colas, streams y exchanges,
cuántos mensajes esperan y quién los toma, y lees los mensajes de un stream
como filas. Cómo funcionan las conexiones en general está en la página
[Conexiones](connections.md).

## Qué puedes ver

- Los hosts virtuales, y en cada uno sus colas, streams y exchanges
- Cuántos mensajes esperan en una cola y cuántos se tomaron sin confirmar
- Quién consume de una cola, y los mensajes que entran y salen por segundo
- Qué está vinculado a qué: los exchanges de una cola, las colas de un exchange
- Los mensajes de un stream como filas, recientes primero, desde offset o fecha
- Los campos de los mensajes JSON, cada uno en su propia columna
- Los mensajes de un stream o los vínculos descargados como archivo
- Los informes del broker: resumen, nodos, alarmas, conexiones, canales
- Mensajes por segundo y lo que espera en cada cola en un panel
- Colas, streams y exchanges encontrados por nombre
- rabbitmqadmin, configurado para la conexión, en una terminal

## Qué puedes cambiar

- Mensajes enviados a un stream, de uno en uno o pegados como filas
- Un mensaje publicado a un exchange o a una cola
- Colas, streams y exchanges nuevos, y borrarlos
- Vínculos creados y quitados
- Una cola purgada, o un vistazo único a sus mensajes
- Todo lo que rabbitmqadmin puede cambiar, escrito en la terminal

## Conexión

La página **Conexión** de la ventana pide:

- **Host** y **Puerto AMQP**: dónde acepta AMQP el broker, 5672 por defecto,
  5671 con TLS;
- **Dirección de administración**: dónde responde su API de administración.
  Vacío significa `http://`, el host y el puerto 15672, o `https://` con TLS.
  RabbitMQ solo responde ahí con su plugin de administración activo; las
  imágenes oficiales `-management` lo tienen;
- **Usuario** y **Contraseña**: un solo usuario de RabbitMQ para ambos;
- **Host virtual**: vacío para todos los hosts virtuales que el usuario puede
  ver, o un nombre, como `/`;
- **TLS** y **Certificado CA**: una conexión cifrada, y la autoridad que firmó
  el certificado del broker cuando el sistema no confía en ella.

Una cadena de conexión `amqp://user:password@host:5672/vhost` rellena el
formulario; `amqps://` es TLS, y `%2F` en la ruta es el host virtual `/`.

La comprobación pregunta primero a la API de administración y luego a AMQP.
Cuando solo AMQP se niega — un host virtual que el usuario no puede abrir, un
puerto inalcanzable —, la conexión se guarda igualmente y dice por qué: el
catálogo funciona, los mensajes de un stream no. No se admite túnel SSH.

## El catálogo

- Con varios hosts virtuales, arriba aparece su lista; con uno, o con uno
  nombrado en la conexión, arriba están sus **Colas**, **Streams** y
  **Exchanges**.
- Una cola dice su tipo (classic o quorum), cuántos mensajes esperan, cuántos
  se tomaron y aún no se confirmaron, y cuántos consumidores tiene.
- Un stream dice cuántos mensajes guarda y quién lo lee.
- Un exchange dice su tipo: direct, topic, fanout o headers. Tus exchanges van
  primero, luego los que RabbitMQ crea en cada host virtual; el exchange
  predeterminado, que no tiene nombre, es **(predeterminado)**.
- Los números son las mediciones de RabbitMQ cada pocos segundos, así que un
  número puede ir un instante por detrás.
- Un nivel muestra los primeros quinientos por nombre.

## Una cola y un exchange

Una cola guarda un mensaje hasta que un consumidor lo toma y luego lo olvida,
así que sus mensajes no se muestran: leerlos sería quitarlos.

- Una cola se abre con sus vínculos: el exchange que le envía, la clave de
  enrutamiento y los argumentos. Toda cola está vinculada al exchange
  predeterminado por su propio nombre.
- Un exchange se abre con sus destinos: la cola o el exchange, la clave de
  enrutamiento y los argumentos.

## Los mensajes de un stream

Un stream guarda sus mensajes durante su retención, como un registro, y
cualquiera puede leerlo desde cualquier punto sin quitar nada.

- Una fila por mensaje: su offset, su hora, el exchange y la clave de
  enrutamiento por los que llegó, su tipo de contenido, cabeceras, demás
  propiedades y cuerpo.
- Cuando los cuerpos son objetos JSON, cada campo es también una columna,
  llamada `body.` y el campo. Los campos salen de los doscientos mensajes más
  recientes.
- Un cuerpo que no es texto se muestra en hexadecimal.
- Los más recientes primero. Ordena por **offset** para empezar por los más
  antiguos; ninguna otra columna ordena.
- **timestamp** es la hora que el emisor puso en el mensaje, vacía si no puso
  ninguna. Filtrarlo «desde» un momento empieza a leer donde el propio stream
  recibió ese momento, con la precisión de un bloque de mensajes.
- Filtra por **offset** para elegir dónde empieza y termina la lectura.
- Los filtros en las demás columnas recorren los mensajes leídos, hasta cien
  mil por página.
- Una página llega como mucho a diez mil mensajes desde el final. Para ir más
  atrás, filtra por offset o por fecha.
- Leer un stream no le quita nada ni mueve el lugar de nadie.

## El panel de detalles

Selecciona una cola, un stream o un exchange y elige **Detalles** en el menú
del catálogo.

- Una cola: su tipo, estado, mensajes en espera y sin confirmar, mensajes que
  entran y salen por segundo, su nodo y política, cada consumidor con su canal
  y prefetch, y los argumentos con que se creó.
- Un stream: sus mensajes, segmentos, mensajes que entran por segundo, cuándo
  llegó su mensaje conservado más antiguo, su líder y miembros, sus
  consumidores y argumentos.
- Un exchange: su tipo, si sobrevive a un reinicio, si se borra sin uso o es
  interno, y sus mensajes que entran y salen por segundo.

## Enviar mensajes a un stream

- **+** sobre las filas de un stream añade un mensaje. Rellena lo que
  necesites: todo puede quedar vacío. Pasa por el exchange predeterminado, con
  el nombre del stream como clave de enrutamiento.
- **body** es texto; `0x` seguido de dígitos hexadecimales se envía como esos
  bytes. Déjalo vacío y rellena los campos `body.` para enviar un objeto JSON
  con ellos.
- **headers** es un objeto JSON, como `{"source": "manual"}`; **properties**
  es un objeto JSON de lo que AMQP nombra: `message_id`, `correlation_id`,
  `reply_to`, `priority`, `expiration`, `type`, `app_id`, `delivery_mode`.
- Un **timestamp** vacío no envía ninguno.
- Las filas pegadas en un stream se envían como mensajes. Si un valor no se
  puede leer, no se envía nada y se indica la celda.
- La fila nueva no muestra offset hasta que se vuelve a leer la página: lo da
  el stream.

## Cambiar colas, streams y exchanges

Marca una cola, un stream o un exchange, o nada en su nivel, y abre el menú
del catálogo:

- **Nueva cola**, **Nuevo stream**, **Nuevo exchange** — cada uno en su nivel.
  Una cola es classic o quorum; un stream guarda mensajes durante un tiempo
  como `7D` y hasta un tamaño; los argumentos son un `nombre=valor` por línea,
  como `x-max-length=10000`.
- **Publicar** — un mensaje a un exchange con clave de enrutamiento, o a una
  cola. Un mensaje que el exchange no enruta a ninguna cola se pierde, y la
  ventana lo dice.
- **Vincular** — desde un exchange a la cola marcada, o desde el exchange
  marcado a una cola o exchange, con clave de enrutamiento. **Desvincular**
  elige uno de los vínculos del nodo marcado.
- **Purgar** — se van todos los mensajes listos de una cola; los que los
  consumidores tomaron y aún no confirmaron se quedan con ellos.
- **Borrar** — la ventana dice cuántos mensajes y vínculos se van. Los
  exchanges propios de RabbitMQ no se borran.

## Echar un vistazo

Los mensajes de una cola no se muestran al abrirla: leerlos sería tomarlos.
**Echar un vistazo** toma hasta cien, los devuelve al momento y abre lo leído
en una pestaña.

- Cada mensaje vuelve marcado como **reentregado**. Una cola quorum cuenta el
  vistazo para su límite de entregas, tras el cual un mensaje va a dead-letter
  o se descarta, y un consumidor puede recibir los mensajes fuera de orden. La
  ventana pregunta antes de mirar.
- La pestaña es el vistazo tal como se tomó. Recorrerla no vuelve a leer la
  cola; para un vistazo nuevo, vuelve a echarlo.
- Un vistazo se guarda mientras DataPlayer funciona, y un tiempo después de
  abrirse por última vez.

## La sección Broker

Arriba del catálogo, **Broker** reúne lo que el broker dice de sí mismo:

- **Resumen** — la versión, cuántas conexiones, canales, colas, exchanges y
  consumidores, los mensajes listos y sin confirmar, y los mensajes por segundo
  de entrada y salida;
- **Nodos** — la memoria de cada nodo y su límite, el disco libre y su umbral,
  los descriptores de archivo y el tiempo en marcha;
- **Alarmas** — un nodo sin memoria o disco suficientes. Mientras haya una
  alarma, RabbitMQ bloquea a todos los emisores; el informe está vacío cuando
  todo va bien;
- **Conexiones** y **Canales** — cada cliente, su usuario y host virtual, sus
  canales, consumidores, prefetch y mensajes tomados sin confirmar;
- **Políticas** — cada política, a qué se aplica y qué fija.

Resumen, Alarmas y Conexiones se actualizan cada diez segundos. Una lista larga
muestra sus primeros quinientos y lo dice.

## Paneles y búsqueda

- El panel **Broker de RabbitMQ** dibuja los mensajes por segundo, lo que
  espera en cada cola y lo tomado sin confirmar, las conexiones y las alarmas,
  para las primeras cien colas por nombre.
- La búsqueda de la cabecera encuentra colas, streams y exchanges por nombre,
  en cada host virtual que ve la conexión.

## Descargas

**Descargar** en un stream guarda los mensajes que mostraría su página, con
sus filtros y orden, hasta diez mil. Una cola o un exchange descarga sus
vínculos.

## rabbitmqadmin

**Terminal** en una conexión de RabbitMQ abre bash con `rabbitmqadmin`, el
cliente de línea de comandos de RabbitMQ para la API de administración, ya
apuntado a la conexión: su dirección, usuario, contraseña y host virtual. Tab
completa sus comandos. Prueba:

- `rabbitmqadmin show overview` — el broker de un vistazo
- `rabbitmqadmin list queues` — todas las colas con sus contadores
- `rabbitmqadmin list exchanges` — los exchanges
- `rabbitmqadmin -V NOMBRE list queues` — otro host virtual

Puede declarar, borrar y purgar colas y exchanges, publicar y obtener mensajes
y exportar definiciones; lo que cambia se cambia en el broker al momento. La
terminal se ejecuta en un contenedor en el servidor de DataPlayer, así que ese
servidor debe poder iniciar contenedores, y la dirección de administración
debe ser accesible desde allí.
