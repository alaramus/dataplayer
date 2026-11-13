# Servicios y terminales

DataPlayer puede iniciar por usted servidores de bases de datos y otras fuentes en la máquina donde se ejecuta, y abrir terminales sobre sus conexiones. Ambas cosas viven en el panel del pie de la pantalla, que se abre con sus herramientas en la barra izquierda inferior.

## Iniciar un servidor aquí

Cuando esta instalación puede ejecutar contenedores, el panel de un tipo de fuente en **Nueva conexión** ofrece **Iniciar … aquí** — PostgreSQL, MySQL, Redis, un servidor SSH y otros. Cómo pregunta y qué obtiene se describe en la página [Conexiones](connections.md). El servidor se ejecuta en Docker en esta máquina, y su conexión se crea por usted.

Un botón atenuado indica por qué al apuntar a él: esta instalación no puede ejecutar contenedores en absoluto, o no ese tipo.

## La herramienta Services

**Servicios** enumera los servidores iniciados aquí para usted, con el estado de cada uno y de su contenedor.

- **Detenerlo** detiene un servidor; lo que tiene guardado se conserva. **Iniciarlo** lo vuelve a iniciar.
- **Empezar de nuevo** elimina un servidor que no arrancó, junto con sus datos, y lo intenta de nuevo.
- **Dónde escucha** muestra el host, el puerto, el usuario y la base de datos para llegar desde sus propias herramientas, y una cadena de conexión. Su contraseña se muestra solo una vez, al crear el servidor, salvo que usted haya escrito una propia.
- **Lo que imprimió** muestra la salida del propio servidor.
- **Eliminar este servicio** elimina el servidor y todo lo que tiene guardado. **Eliminar también la conexión** elimina también su conexión.

Iniciar, detener y eliminar se ejecutan en segundo plano; la campana de actividad muestra cómo van.

## Terminales

**Terminales** abre un terminal sobre una de sus conexiones:

- en una conexión SSH, una shell en ese servidor;
- en una conexión a base de datos que lo ofrezca, su propio programa cliente — `psql`, `mysql`, `cqlsh`, `zkCli`, las herramientas de Kafka, `rabbitmqadmin` y otros — con la sesión iniciada como esa conexión. Se ejecuta en un contenedor que este servidor inicia, así que solo se ofrece donde se permiten los contenedores. La página de cada tipo de fuente indica lo que abre.

Pueden estar abiertos varios terminales a la vez, cada uno en una pestaña del panel. Un terminal se queda con todas las teclas, Ctrl+K incluido. Cerrar su pestaña lo termina.

Los terminales solo se abren sobre conexiones que le pertenecen.

## Copias de seguridad

Una base de datos que puede copiarse fuera tiene **Copias de seguridad** en el menú de acciones de su catálogo: **Copiar esta base de datos fuera** crea una copia de seguridad, un archivo en su propio almacenamiento; **Restaurar** la escribe de nuevo, reemplazando lo que contenga; borrar elimina el archivo. La página de cada tipo de fuente indica si tiene copias de seguridad.

## Registros

**Registros**, en la barra izquierda inferior de un administrador, lee el registro propio del servidor: filtrado por nivel y por proceso, buscado por texto, por la referencia que da un mensaje de error o por una ruta, y seguido a medida que crece.
