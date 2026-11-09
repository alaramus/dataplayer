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

## Qué puedes cambiar

- Nada todavía: esta versión solo lee

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

## Descargas

**Descargar** en un stream guarda los mensajes que mostraría su página, con
sus filtros y orden, hasta diez mil. Una cola o un exchange descarga sus
vínculos.
