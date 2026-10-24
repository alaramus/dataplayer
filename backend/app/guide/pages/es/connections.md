# Conexiones

Una conexión es una forma guardada de llegar a una fuente: una base de datos
PostgreSQL, un servidor Redis, una carpeta de tus propios archivos o un servidor
por SSH. Los catálogos, las tablas, las consolas de consultas, los flujos y los
cuadros de mando funcionan todos a través de conexiones.

Cada tipo de fuente tiene su propia página: [Archivos](source-file.md),
[PostgreSQL](source-postgres.md), [Redis](source-redis.md) y
[SSH](source-ssh.md).

## La lista de conexiones

La columna **Conexiones** está a la izquierda del espacio **Datos**. El espacio
**Flujos** muestra la misma lista.

- Pulsa el nombre de una conexión para abrir su catálogo. Se abre en la columna
  junto a la lista, como una pestaña con el nombre de la conexión.
- Pulsa el icono de una conexión para abrir su ventana, donde se edita.
- **+** al principio de la columna añade una conexión.
- La lupa convierte el encabezado en un filtro por nombre. **Es** o la cruz lo
  cierran.
- La flecha al final del encabezado vuelve a leer la lista.
- El botón de la esquina superior izquierda de la pantalla reduce la columna a
  iconos y la vuelve a ensanchar. La columna estrecha sigue abriendo catálogos y
  sigue teniendo **+**.

Un punto en cada icono indica lo que encontró la última comprobación:

- verde: la fuente respondió;
- rojo: la fuente no respondió o rechazó la conexión;
- amarillo: la conexión está desactivada;
- gris: aún no se ha comprobado.

Las conexiones se comprueban mientras el espacio de trabajo está abierto. La
frecuencia se establece en la página **Preferencias**.

## Añadir una conexión

1. Pulsa **+** al principio de **Conexiones**. Se abre la ventana **Nueva
   conexión**.
2. Elige un tipo de fuente. Los tipos están agrupados a la izquierda: **Bases de
   datos SQL**, **Almacenes clave-valor**, **Archivos y almacenamiento**. El
   cuadro de búsqueda encuentra un tipo por su nombre o por lo que puede hacer.
3. El panel de la derecha indica qué es el tipo, qué puedes ver y cambiar a
   través de él, y tiene **Guía**, que abre su página de esta guía.
4. Pulsa **Crear conexión**, o haz doble clic en el tipo. Se abre su ventana de
   conexión.
5. Rellena los campos, pulsa **Probar conexión** y luego **Aceptar** para
   guardar y cerrar, o **Aplicar** para guardar y mantener la ventana abierta.
   **Atrás** vuelve a la lista de tipos sin guardar.

Cuando este servidor puede ejecutar contenedores, el panel también ofrece
iniciar un nuevo servidor de ese tipo en esta máquina: **Iniciar PostgreSQL
aquí**, **Iniciar TimescaleDB aquí**, **Iniciar Redis aquí** o **Iniciar servidor
SSH aquí**. La ventana que se abre pregunta **Cómo**:

- automáticamente: el servidor recibe un nombre por ti, obtiene una contraseña
  que nadie tiene que elegir y viene con datos de ejemplo, para que haya algo
  que mirar;
- con tus propias opciones: un nombre, un usuario, una base de datos, un puerto
  en esta máquina y, para un servidor SSH, si inicias sesión con una contraseña
  o con una de tus claves SSH.

En cualquiera de los dos casos, la conexión se crea por ti. El progreso del
inicio se muestra en la campana de actividad de la esquina inferior derecha.
Cuando el servidor está listo, una ventana muestra dónde llegar a él desde tus
propias herramientas y su contraseña, una sola vez. Copia la contraseña entonces
si la necesitas en otro lugar.

Un botón atenuado explica por qué cuando pasas el puntero sobre él: puede que
esta instalación no pueda ejecutar contenedores en absoluto.

## La ventana de conexión

La ventana de una conexión se abre cuando añades una o pulsas su icono. Puede
haber varias abiertas a la vez, de modo que puedes leer una conexión mientras
rellenas otra. Al cerrar una ventana con cambios sin guardar, se pregunta
primero.

- **Nombre** es como aparece la conexión en la lista. Es obligatorio.
- **Color de la pestaña** colorea las pestañas de la conexión y su fila en la
  lista.
- **En uso** desactiva la conexión sin eliminarla. Una conexión desactivada
  conserva sus ajustes, no se puede abrir y tiene un punto amarillo.
- **URL** es la cadena de conexión compuesta a partir de los campos. La
  contraseña nunca forma parte de ella. Pega una cadena de conexión en ella y
  los campos se rellenan a partir de ella. El botón de copiar de al lado copia
  la cadena.
- **Probar conexión** intenta conectar con lo que contiene el formulario ahora,
  esté guardado o no. La respuesta aparece en un pequeño emergente sobre el
  botón.
- **Eliminar** quita la conexión. Solo la tiene su propietario, y pregunta
  primero.

La ventana tiene al menos tres páginas.

### Conexión

Cómo llegar a la fuente. Los campos dependen del tipo de fuente y se describen
en su página. Una opción de **Autenticación** cambia qué campos se muestran.

### Opciones

**Conservar respuestas** indica cuánto tiempo se puede reutilizar un nivel del
catálogo y una página de filas antes de volver a leer la fuente.

- **Según decida esta fuente** es la opción predeterminada. La etiqueta indica
  cuánto tiempo es.
- **No conservar nunca las respuestas** lee la fuente cada vez.
- **Conservar durante …** establece un tiempo propio, de hasta un día.

Pulsar un botón de recarga siempre lee la fuente, sea cual sea la opción elegida
aquí. Una pequeña marca junto al botón de recarga dice **En vivo** mientras la
respuesta en pantalla es reciente y viene de la fuente, y muestra un reloj
cuando es una respuesta conservada. Pasa el puntero sobre ella para ver su
antigüedad.

Una fuente que no conserva nada lo indica, y el campo está desactivado.

### Permisos

- **Consolas** decide qué puede hacer una consola de consultas en esta conexión:
  **Solo lectura**, **Preguntar antes de escribir** (la opción predeterminada) o
  **Escritura permitida**. Se aplica a todas las personas con las que se comparte
  la conexión.
- **Permitir enviar datos a terceros** decide si los datos leídos a través de
  esta conexión se pueden enviar a un servicio externo, como un proveedor de
  modelos de IA. Está desactivado a menos que lo actives.
- **Quién más puede acceder** enumera a las personas con las que se comparte la
  conexión y las solicitudes que esperan una respuesta. **Compartir** la entrega
  a alguien.

## Compartir una conexión

Una conexión pertenece a la persona que la creó. El propietario puede dar a otras
personas uno de tres niveles:

- **Lectura**: abrir el catálogo, leer filas, descargarlas y crear gráficos con
  ellas;
- **Editar filas**: además, cambiar, añadir y eliminar filas;
- **Cambiar estructura**: además, cambiar columnas, índices, claves y tablas.

Un nivel abarca toda la conexión, no una tabla. Solo el propietario puede
eliminar la conexión, cambiar sus ajustes, hacer una copia de seguridad o
compartirla con más personas.

Una conexión compartida aparece en la lista de la otra persona. Su ventana
muestra quién la compartió y con qué nivel, y sus campos no se pueden cambiar.

Una tabla también se puede compartir como enlace: **Compartir esta vista** en la
fila de comandos sobre una tabla crea un enlace a esa tabla con sus filtros y
columnas. Un enlace no da acceso por sí mismo. Quien lo abra sin acceso a la
conexión puede solicitarlo, y la solicitud aparece en la página **Permisos** del
propietario y en su campana de actividad. El propietario elige el nivel cuando
la aprueba.

## Abrir un catálogo

Pulsar una conexión abre su catálogo: lo que contiene la fuente, nivel a nivel o
como un árbol, según el tipo de fuente. Un catálogo tiene su propia fila de
comandos en la parte superior y un menú de acciones sobre lo que está marcado.
Los comandos dependen del tipo de fuente y se describen en su página.

Cosas que aparecen en todos los catálogos:

- marcar un nodo y abrir el menú de acciones actúa sobre lo marcado, o sobre el
  nivel en el que estás cuando no hay nada marcado;
- **Detalles** indica qué es un nodo: su tamaño, sus fechas, en qué se puede
  abrir;
- **Copiar** y **Cortar** toman nodos, y **Pegar** los coloca donde estás, en la
  misma conexión o en otra;
- abrir un nodo lo abre en una pestaña propia en la columna de trabajo, como
  filas, como documento, como imagen, etc.;
- el catálogo se puede duplicar junto a sí mismo, o emparejar con el catálogo de
  otra conexión en una ventana, para mover cosas entre los dos.
