# Docker

Un demonio Docker en otra máquina, alcanzado mediante una de tus conexiones
SSH. Ves sus contenedores, imágenes, volúmenes y redes, lo que el demonio dice
de cada uno, los registros y procesos de un contenedor y los informes del
propio demonio. Cómo funcionan las conexiones en general está en la página
[Conexiones](connections.md).

## Qué puedes ver

- Contenedores, agrupados por proyecto de Compose, en marcha o no
- Imágenes, volúmenes y redes, y qué contenedores los usan
- Lo que el demonio dice de cualquiera de ellos, como árbol JSON
- Los registros de un contenedor, lo más reciente primero, y sus procesos
- Las capas de una imagen y las instrucciones que las crearon
- El motor: versiones, controladores, CPU, memoria, disco, eventos

## Conexión

Al demonio nunca se llega directamente. Crea primero una **conexión SSH** a la
máquina donde corre; después la página **Conexión** de una conexión Docker
pide:

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

- Un contenedor, una imagen, un volumen o una red se abre como lo que el
  demonio dice de él, en árbol JSON. El de un contenedor incluye su entorno,
  que a menudo guarda contraseñas: cualquiera con quien compartas esta
  conexión lo ve.
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

## Lo que Docker aún no tiene aquí

- Arrancar, detener, reiniciar y eliminar contenedores
- Eliminar y limpiar imágenes, volúmenes y redes; descargar imágenes
- Una terminal dentro de un contenedor, y registros que se siguen en vivo
- Métricas en un panel, y la búsqueda
- Un demonio alcanzado por TLS en lugar de SSH
