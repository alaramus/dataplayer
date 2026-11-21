# Docker

Un demonio Docker en otra máquina, alcanzado mediante una de tus conexiones
SSH o por TCP con TLS. Ves sus contenedores, imágenes, volúmenes y redes, lo que el demonio dice
de cada uno, los registros y procesos de un contenedor y los informes del
propio demonio. Cómo funcionan las conexiones en general está en la página
[Conexiones](connections.md).

## Qué puedes ver

- Contenedores, agrupados por proyecto de Compose, en marcha o no
- Imágenes, volúmenes y redes, y qué contenedores los usan
- Lo que el demonio dice de cualquiera de ellos, como árbol JSON
- Un contenedor de un vistazo, con sus secretos ocultos hasta pedirlos
- Los registros de un contenedor según se escriben, y sus procesos
- Las capas de una imagen y las instrucciones que las crearon
- El motor: versiones, controladores, CPU, memoria, disco, eventos
- CPU, memoria, red y disco de los contenedores en marcha en un panel

## Qué puedes cambiar

- Contenedores arrancados, detenidos, reiniciados, pausados o matados
- Los contenedores de un proyecto de Compose, todos a la vez
- Contenedores, imágenes, volúmenes y redes eliminados
- Contenedores detenidos e imágenes, volúmenes y redes sin uso limpiados
- Nuevos volúmenes y redes
- Imágenes públicas descargadas, y un contenedor guardado en una imagen
- Un shell dentro de un contenedor en marcha, en una terminal
- El contenedor de una base de datos abierto como conexión propia

## Conexión

**Transporte** elige cómo se llega al demonio: **Socket por SSH** o **TCP con
TLS**, más abajo. Para el socket, crea primero una **conexión SSH** a la
máquina donde corre el demonio; después la página **Conexión** pide:

- **Conexión SSH**: una de tus conexiones SSH. Su cuenta debe poder usar el
  socket del demonio; en la mayoría de máquinas, está en el grupo `docker`;
- **Socket**: dónde escucha el demonio en esa máquina. `/var/run/docker.sock`
  para Docker, `/run/user/<uid>/docker.sock` para Docker sin root. La tarjeta
  **Podman** rellena `/run/podman/podman.sock`; un Podman sin root usa
  `/run/user/<uid>/podman/podman.sock`, y su socket debe estar activado
  (`systemctl --user enable --now podman.socket`).

El socket se reenvía por la conexión SSH, igual que una base de datos se
alcanza por un túnel SSH; el servidor SSH debe permitirlo
(`AllowStreamLocalForwarding`, activado por defecto). Si la comprobación dice
que el socket no pudo abrirse, falla una de tres cosas, y OpenSSH no dice
cuál: nada escucha en esa ruta, la cuenta no puede usarlo, o el reenvío está
desactivado.

El demonio debe hablar la API 1.41 o más reciente (Docker 20.10 en adelante).

El demonio Docker de la máquina donde corre el propio DataPlayer nunca se
ofrece: quien tiene ese socket tiene la máquina.

## Por TCP con TLS

A un demonio que escucha en TCP con TLS mutuo — `dockerd --tlsverify`,
normalmente en el puerto 2376 — se llega sin SSH. El formulario pide:

- **Host** y **Puerto**: el host tal como lo nombra el certificado del demonio;
- **Certificado de CA**: `ca.pem`, la autoridad que firmó el del demonio;
- **Certificado de cliente** y **Clave de cliente**: `cert.pem` y `key.pem`,
  que el demonio acepta. La clave no debe estar cifrada.

Pega cada archivo entero, con la línea `-----BEGIN`. **Túnel SSH** queda en
**Directamente** salvo que el puerto solo se alcance desde otra red; entonces
el host es el nombre con que lo alcanza el servidor SSH.

Un demonio en TCP sin TLS — puerto 2375 — se rechaza, y la comprobación lo
dice: quien alcanza ese puerto es dueño de la máquina. También dice qué falló:
un certificado que la CA no firmó, un host para el que el certificado no es, o
un certificado de cliente que el demonio no acepta.

## El catálogo

- **Sistema** contiene los informes del demonio, abajo.
- **Contenedores** tiene una carpeta por proyecto de Compose, nombrada por la
  etiqueta que escribe Compose, y **Sin proyecto** para el resto. Cada
  contenedor muestra su estado en una palabra — en marcha, sano, enfermo,
  arrancando, en pausa, reiniciando, detenido, fallido, creado o muerto — con
  el estado del propio demonio al lado, su imagen, su servicio de Compose y
  sus puertos publicados.
- **Imágenes** lista cada imagen por su id, con etiqueta o sin ella, con su
  tamaño y cuántos contenedores la usan.
- **Volúmenes** lista cada volumen por nombre; **Redes** cada red, primero
  las tres de Docker, cada una marcada como integrada, de Compose o de
  usuario.
- Cada una de estas carpetas se abre también como tabla, que se puede
  filtrar y ordenar por cualquier columna. Más de diez mil de un mismo tipo
  no se listan.

## Cómo se abre un nodo

- **Inspeccionar** de un contenedor se abre en su **Resumen**: el estado, la
  imagen, cuándo se creó e inició o cómo terminó, la política y el número de
  reinicios, el comando, la comprobación de salud y sus últimos resultados,
  los puertos publicados, las redes con sus direcciones, los montajes, el
  entorno, las etiquetas y los límites. Un aviso dice si se reinició más de
  tres veces o se detuvo por falta de memoria. La imagen, un volumen, una
  red y el proyecto de Compose son enlaces que los muestran en el catálogo.
- **Como JSON** cambia la misma pestaña a lo que dice el demonio, en árbol
  JSON, y **Resumen** la devuelve. Una imagen, un volumen o una red se abre
  en árbol JSON.
- Una variable cuyo nombre contiene PASSWORD, PASSWD, SECRET, TOKEN, KEY,
  CREDENTIAL o PRIVATE se muestra como puntos hasta que pulses su ojo, y
  solo se copia una vez mostrada. Eso la oculta de un vistazo, no de quien
  lee: el JSON la muestra tal cual, y cualquiera con quien compartas esta
  conexión ve el entorno de un contenedor.
- Dentro de un contenedor: **Registros** — la hora, el flujo (stdout o
  stderr) y el texto de cada línea, lo más reciente primero, hasta diez mil
  líneas atrás, una línea cortada a 16 KB — y **Procesos**, lo que corre en él
  ahora. Un contenedor detenido no tiene ninguno.
- Dentro de una imagen: **Historial**, sus capas.
- Dentro de un volumen o una red: **Contenedores**, los que lo usan.

## La sección Sistema

- **Motor**: versiones del demonio, sistema operativo, kernel, controladores,
  CPU, memoria y recuentos de contenedores e imágenes, con los nombres del
  propio demonio. Los espejos de registro y los proxies se omiten: pueden
  contener contraseñas.
- **Uso de disco**: cada imagen, contenedor, volumen y entrada de la caché de
  compilación con su tamaño, y si quitarla liberaría espacio. El demonio mide
  cada volumen para responder, así que puede tardar.
- **Eventos**: lo que pasó en la última hora, lo más reciente primero.

## Cuando algo se rechaza

- Un rechazo de la conexión SSH o del socket detiene toda la conexión, y cada
  pantalla dice por qué.
- Un demonio detrás de un plugin de autorización o un proxy que filtra puede
  rechazar una petición: se dice como **El servidor Docker no lo permitió**.

## Cambiar

Selecciona un contenedor, la carpeta de un proyecto de Compose o un nodo y abre
el menú del catálogo. El ciclo de vida de un contenedor necesita acceso de
escritura; eliminar, limpiar, descargar, guardar y crear volúmenes y redes
necesitan acceso a la estructura.

- **Arrancar**, **Detener**, **Reiniciar**, **Pausar**, **Quitar la pausa** y
  **Matar** actúan sobre los contenedores seleccionados, o sobre todos los de
  un proyecto de Compose seleccionado. Cada uno dice primero qué hará y qué
  contenedores ya lo están. Detener y Reiniciar pueden esperar unos segundos
  antes de matar; Matar envía la señal que elijas.
- **Eliminar contenedor** rechaza uno en marcha sin **Forzar**, y puede
  llevarse sus volúmenes anónimos. **Eliminar imagen** nombra los contenedores
  que la usan; **Eliminar volumen** rechaza uno montado; **Eliminar red**
  rechaza una con contenedores, y las tres de Docker.
- En **Contenedores**, **Imágenes**, **Volúmenes** y **Redes**, la limpieza
  lista lo que se irá y, para las imágenes, el espacio que libera. El demonio
  limpia lo que esté sin uso al pulsar, así que también se va lo que quedó sin
  uso entretanto.
- **Nuevo volumen** y **Nueva red** están en **Volúmenes** y **Redes**.
- **Descargar imagen** en **Imágenes** y **Guardar en una imagen** sobre un
  contenedor se ejecutan como tareas en **Actividad**. Solo se descargan
  imágenes públicas: un registro que pide iniciar sesión no se admite.

## Una terminal dentro de un contenedor

Selecciona un contenedor en marcha y elige **Terminal** en el menú del
catálogo. Elige el shell — `/bin/sh` está en casi cualquier imagen, `/bin/bash`
y `/bin/ash` en algunas — y si se ejecuta como root en lugar del usuario de la
imagen. Se abre en **Terminales** al pie de la ventana, con el nombre del
contenedor, y termina al cerrarla. Solo el propietario de la conexión puede
abrir una. Un contenedor sin el shell elegido lo dice; vuelve a abrirla con
otro.

## Registros y niveles al día

Mientras los **Registros** de un contenedor están abiertos, las líneas nuevas
aparecen según el contenedor las imprime, como mucho cada dos segundos. El
nivel del catálogo en el que estás se vuelve a leer cuando el demonio lo
cambia: un contenedor que se detiene, una imagen descargada, un volumen
eliminado — por DataPlayer o por cualquier otro.

## Métricas en un panel

Activa el envío de métricas de la conexión y añade a un panel el diseño
**Contenedores Docker**. Cada sondeo mide hasta cincuenta contenedores en
marcha, por nombre: CPU —100% es una CPU ocupada del todo, así que puede pasar
de 100%—, memoria sin la caché que el sistema puede recuperar, tráfico de red
y de disco por segundo, y los procesos de cada uno. También cuenta los
contenedores en marcha, en pausa y detenidos; **Contenedores sin medir** cuenta
los que pasan de cincuenta. Un sondeo tarda alrededor de un segundo: el
demonio mide cada contenedor dos veces para saber su uso de CPU.

## Búsqueda

La búsqueda del catálogo y la búsqueda sobre todo encuentran por nombre
contenedores, proyectos de Compose, imágenes por cualquiera de sus etiquetas,
volúmenes y redes. Dentro de una carpeta, busca solo en esa carpeta.

## El contenedor de una base de datos como conexión

Selecciona un contenedor de PostgreSQL, MySQL, MariaDB, Redis, MongoDB o
ClickHouse y elige **Abrir como conexión**. Se abre el formulario de una
conexión nueva, rellenado a partir del contenedor:

- la misma conexión SSH, como su túnel SSH;
- el puerto publicado en `127.0.0.1`, o si no la dirección del contenedor;
- el usuario, la contraseña y la base con que se inició el contenedor.

Revísalo y guárdalo. Una imagen se reconoce por su nombre en Docker Hub, como
`postgres` o `mariadb`; una de otro registro, no. La imagen oficial de Redis
recibe su contraseña en la línea de órdenes, así que escríbela tú. Solo el
propietario de la conexión Docker puede hacerlo, porque el formulario lleva las
contraseñas del contenedor.

## Lo que Docker aún no tiene aquí

- Registros privados, y crear o ejecutar contenedores nuevos
