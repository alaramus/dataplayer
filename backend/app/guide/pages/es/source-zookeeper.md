# ZooKeeper

Un servidor ZooKeeper. Recorres su árbol de znodes, lees los datos de un znode
con su stat y su ACL, editas los datos y recorres por páginas los hijos de un
znode como filas. Cómo funcionan las conexiones en general se explica en la
página [Conexiones](connections.md).

## Qué puedes ver

- El árbol de znodes, desplegado donde estás
- Los datos de un znode: JSON como árbol, texto como texto, el resto en hex
- El stat de un znode: versiones, zxid, hijos, sesión de uno efímero
- La ACL de un znode: quién puede leer, escribir, crear, borrar, administrar
- Los hijos de un znode como filas, por páginas
- zkCli, conectado al servidor y a la ruta raíz, en un terminal
- Los informes del servidor: modo, contadores, clientes, watches, ajustes
- Los contadores del servidor en un panel
- Znodes encontrados por su nombre
- Todos los hijos de un znode, descargados en un archivo

## Qué puedes cambiar

- Los datos de un znode, escritos enteros frente a la versión leída
- Znodes nuevos, en la cima o dentro de otro, normales o secuenciales
- Borrar znodes, solos o con todo lo que tienen debajo
- La ACL de un znode, y la de todo lo que tiene debajo
- Todo lo que zkCli puede cambiar, escrito en su terminal

## Conexión

La página **Conexión** de la ventana pide:

- **Host** y **Puerto** de un servidor del ensemble, 2181 si no escucha en
  otro;
- **Ruta raíz**: todo se lee bajo esta ruta como si fuera la cima, y nada por
  encima es accesible. Déjala vacía para el árbol entero;
- **TLS**: una conexión cifrada, con el certificado del servidor comprobado;
- **Autenticación**: **Anónimo**, o un usuario **Digest** y su contraseña,
  añadidos a la sesión al abrirse.

Una cadena de conexión como `zk.example.com:2181/apps/billing`, pegada en
**URL**, rellena estos campos. No se admite una lista de servidores: indica uno.

## El catálogo

- El árbol se abre en la cima o en la ruta raíz. Un znode con hijos tiene una
  flecha; un clic en su nombre lo abre.
- Cada znode dice cuántos datos tiene, cuántos hijos tiene y si es efímero.
- `/zookeeper` pertenece al servidor y está marcado como tal.
- Un nivel muestra sus primeros mil hijos por nombre. La tabla de hijos del
  znode de arriba los recorre todos.
- Un znode que esta conexión no puede leer aparece solo con su nombre y marcado
  **sin acceso**. ZooKeeper pide permiso de lectura incluso para decir su tamaño.

## Los datos de un znode

- Los datos JSON de hasta 4 KB se abren como árbol; también pueden abrirse como
  texto.
- Los demás datos se abren como texto en un editor. Guardar los escribe enteros.
- Solo se guarda si nadie ha cambiado el znode desde que lo abriste, y solo si
  sigue siendo el mismo znode y no uno borrado y creado de nuevo. Si ha
  cambiado, vuelve a cargarlo y haz el cambio otra vez.
- El JSON sigue siendo JSON: un guardado que no se puede analizar se rechaza.
- Los datos que no son texto UTF-8 se muestran en hexadecimal y no se editan
  aquí.

## Los hijos como filas

- Una fila por hijo: su nombre, el comienzo de sus datos, su tamaño, versión,
  número de hijos, cuándo se cambió y se creó, y la sesión de uno efímero.
- Las filas van en el orden de sus nombres. No se pueden ordenar ni filtrar:
  ZooKeeper no tiene índice para ello.
- Los datos de más de 4 KB no se leen para la tabla y su celda queda vacía; abre
  el znode para leerlos.

## El panel de detalles

Selecciona un znode en el árbol y elige **Detalles** en el menú del catálogo.

- El stat del znode: versiones de datos, hijos y ACL, los zxid de su creación,
  último cambio y último cambio de sus hijos, y su número de hijos.
- La sesión a la que pertenece un znode efímero.
- Una línea por entrada de su ACL: el esquema, el id y lo que permite.

## La sección Servidor

En la cima del árbol, **Servidor** contiene lo que el servidor dice de sí mismo:
**Servidor** (versión, modo, latencia, conexiones, número de znodes),
**Monitorización** (cada contador), **Conexiones** (cada cliente), **Watches** y
**Configuración**. Los cuatro primeros se vuelven a leer cada diez segundos.

ZooKeeper solo los responde si su ajuste `4lw.commands.whitelist` lo permite;
desde ZooKeeper 3.5 solo `srvr` está permitido si el servidor no dice otra cosa.
Un informe que el servidor no responde muestra una fila con la palabra que hay
que añadir, por ejemplo `4lw.commands.whitelist=srvr,mntr,cons,wchs,conf`.

Los mismos contadores pueden dibujarse en un panel: la plantilla **Servidor
ZooKeeper** muestra paquetes, znodes, latencia, conexiones, peticiones
pendientes y watches. Necesita que `mntr` esté permitido.

## Encontrar znodes

Escribe en el campo sobre el árbol y pulsa el botón de búsqueda para revisar los
nombres de todos los znodes bajo la cima, o bajo el seleccionado. ZooKeeper no
tiene índice de nombres, así que la búsqueda recorre el árbol; se detiene tras
cincuenta mil znodes o cuando se acaba su tiempo, y lo dice. Los niveles que esta
conexión no puede listar se saltan, y la respuesta dice que la búsqueda puede
estar incompleta. Los znodes encontrados se muestran en su sitio del árbol.

## Descargas

La tabla de hijos de un znode se puede descargar entera, en el orden de los
nombres. Un informe también se puede descargar.

## Crear y borrar znodes

Selecciona un znode en el árbol y abre el menú del catálogo.

- **Nuevo znode en la cima** crea uno en la cima del árbol o de la ruta raíz.
  **Nuevo znode dentro** crea uno bajo el znode seleccionado. Dale un nombre y,
  si quieres, sus datos como texto. **Secuencial** hace que ZooKeeper añada al
  nombre un número de diez cifras; el znode creado se abre. No se ofrecen
  znodes efímeros: uno desaparecería en cuanto se creara.
- **Borrar** quita los znodes seleccionados. Uno con hijos no se borra.
- **Borrar con los hijos** dice primero cuántos znodes se irán y nombra los
  primeros. Más de diez mil no se borran desde aquí; usa `deleteall` en zkCli.
  `/zookeeper` pertenece al servidor y no se borra.
- **Cambiar ACL** se abre con la ACL que tiene el znode, una entrada por línea
  como las escribe zkCli: `esquema:id:permisos`, los permisos letras de `cdrwa`
  — crear, borrar, leer, escribir, administrar. Por ejemplo, `world:anyone:r`
  deja leer a cualquiera y nada más. **También cada znode debajo** la aplica a
  todo el subárbol. Antes de aplicarla se te avisa si esta conexión ya no podría
  volver a cambiar la ACL.

## zkCli

**Terminal** en una conexión ZooKeeper abre `zkCli`, el cliente que trae
ZooKeeper, conectado al servidor y a la ruta raíz de la conexión. Se ejecuta en
un contenedor que inicia el servidor, así que el servidor debe poder ejecutar
contenedores, y no pasa por un túnel SSH.

A zkCli no se le puede dar una contraseña digest al arrancar: solo la acepta
escrita como comando. En una conexión con usuario **Digest**, el terminal se abre
conectado pero sin iniciar sesión, y la primera línea lo dice. Escribe
`addauth digest usuario:contraseña` para leer y cambiar los znodes cuya ACL pide
ese usuario. La contraseña no se escribe por ti y DataPlayer nunca la muestra.

## Un ZooKeeper propio

**Servicios** puede iniciar un ZooKeeper en esta máquina, si este servidor puede
ejecutar contenedores. No pide contraseña — ZooKeeper no tiene una para todo el
servidor; quién puede hacer qué lo dice la ACL de cada znode — y solo es
accesible desde esta máquina. Responde a los informes de arriba, y su conexión se
crea por ti.

Viene con un laboratorio bajo `/lab`: configuración en JSON, un registro de
instancias de servicios, una elección y una cola de znodes secuenciales,
contadores guardados como bytes, un bloqueo y `/lab/private`, que solo puede
leer el usuario digest `lab` con la contraseña `lab`. Una conexión Digest con ese
usuario muestra la diferencia.

## Lo que ZooKeeper aún no tiene aquí

- Vigilar un znode para ver sus cambios: actualiza a mano
- Copiar znodes a otra conexión, y las copias de seguridad. ZooKeeper no ofrece
  ninguna de las dos cosas por sus clientes: sus copias de seguridad son los
  archivos de instantánea del propio servidor.
