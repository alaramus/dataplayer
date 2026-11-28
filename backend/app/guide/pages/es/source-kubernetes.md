# Kubernetes

Un clúster de Kubernetes al que se llega por su servidor de API: cualquier
clúster — el tuyo, k3s, kind o uno que gestiona una nube. Ves sus espacios de
nombres y cada tipo de objeto que sirve, incluidos los personalizados, como
las propias tablas del clúster, lo que el clúster dice de cada objeto, los
registros de un pod y los informes del clúster. Cómo funcionan las conexiones
en general está en la página [Conexiones](connections.md).

## Qué puedes ver

- Los espacios de nombres y cada tipo de objeto en ellos, agrupados
- Los tipos fuera de espacios de nombres: nodos, volúmenes, clases y más
- Los recursos personalizados, encontrados como los tipos integrados
- Los objetos de un tipo en tabla, como `kubectl get`, ordenables
- El resumen de un objeto: estado, metadatos, condiciones y contenido
- Un objeto como YAML o como árbol JSON
- Los eventos de un objeto y los pods que elige una carga o un servicio
- Los registros de un contenedor, lo más reciente primero
- El clúster: versión, nodos, pods por fase, eventos y recursos de API

## Qué puedes cambiar

- Escalar deployments, stateful sets y replica sets
- Reiniciar deployments, stateful sets y daemon sets, como rollout restart
- Acordonar, desacordonar y vaciar nodos, el vaciado como job
- Suspender, reanudar y ejecutar ahora cron jobs
- Eliminar cualquier objeto, con el ensayo del propio clúster primero
- Editar el YAML de un objeto donde se abre, y objetos nuevos desde YAML

## Conexión

**Iniciar sesión con** elige cómo DataPlayer inicia sesión en el clúster:

- **Un kubeconfig**: pega el archivo o léelo del disco con el botón junto al
  campo. Los certificados y las claves deben estar dentro, no nombrados como
  archivos; `kubectl config view --minify --flatten` escribe uno así.
  **Contexto** nombra el contexto a usar; vacío usa el actual del archivo.
- **Un token**: la dirección `https://` del **Servidor de API**, su
  **Certificado de la CA** y un **Token** bearer, por ejemplo el de una cuenta
  de servicio.
- **Un certificado de cliente**: el servidor de API, su CA, y un
  **Certificado de cliente** y una **Clave de cliente** que el clúster
  acepte. La clave no debe estar cifrada.

Deja **Certificado de la CA** vacío solo para un servidor cuyo certificado
firmó una autoridad pública. Deja **Espacio de nombres** vacío para ver todos
los que puedes listar; nombra uno si tu cuenta solo puede trabajar en él.

Algunos kubeconfig se rechazan, cada uno con su motivo:

- los que inician sesión ejecutando un programa — `gke-gcloud-auth-plugin`,
  `aws`, `kubelogin` y similares: DataPlayer no ejecuta nada en su servidor;
- los que nombran archivos en lugar de contener sus datos;
- los que desactivan la comprobación del certificado del servidor;
- los que inician sesión con usuario y contraseña, que Kubernetes eliminó.

Elige un **Túnel SSH** solo si el servidor de API solo es accesible desde otra
red. El clúster debe ejecutar Kubernetes 1.27 o posterior.

## El catálogo

- **Clúster** contiene los informes del clúster, descritos abajo.
- **Espacios de nombres** lista cada espacio de nombres, primero **Todos los
  espacios de nombres**, que muestra cada tipo en todos ellos con una columna
  **Namespace**.
- Dentro de un espacio de nombres, sus tipos se agrupan: **Cargas de
  trabajo**, **Red**, **Configuración**, **Almacenamiento** y **Otros**. Otros
  contiene cada tipo que sirve el clúster y que no es de los conocidos,
  incluidos los recursos personalizados, cada uno con su grupo de API.
- **Recursos del clúster** contiene los tipos fuera de espacios de nombres,
  agrupados igual, con **Clúster** para nodos, espacios de nombres y
  definiciones.
- Un tipo se abre como tabla con las columnas que `kubectl get` muestra para
  él, con **Created** en lugar de la edad, para poder ordenar. Cada objeto del
  catálogo muestra sus primeras columnas junto a su nombre, como
  `1/1 · Running`. No se listan más de diez mil de un tipo.

## Cómo se abre un objeto

- Haz clic en un objeto para abrir su resumen: tipo, espacio de nombres,
  creación, propietarios y estado, luego aquello por lo que se lee ese tipo —
  el nodo, las direcciones y los contenedores de un pod con sus imágenes,
  estados y reinicios; las réplicas deseadas, listas y actualizadas de un
  deployment; el tipo, las direcciones y los puertos de un servicio; las
  versiones y la capacidad de un nodo; la clase y el tamaño de una
  reclamación de volumen — luego sus condiciones, etiquetas y anotaciones.
- La cabecera del resumen abre el objeto **Como YAML** o **Como JSON** en una
  pestaña propia. Se omiten los campos donde Kubernetes guarda quién cambió
  qué.
- Sus páginas se abren como tablas en pestañas propias: los **Eventos** sobre
  él; los **Pods** que elige un deployment, un stateful set, un daemon set, un
  replica set, un job o un servicio; y los **Registros** de un pod, una
  página por contenedor: hora y texto, lo más reciente primero, hasta diez mil
  líneas, cada una cortada en 16 KB.
- **Los valores de un secreto nunca se muestran.** Su resumen lista sus claves
  y sus tamaños, y su YAML y su JSON ponen un tamaño en lugar de cada valor.

## La sección Clúster

- **Resumen**: la versión, el servidor, el contexto, quién eres para el
  clúster, los nodos listos, las plataformas, y cuántos espacios de nombres y
  pods hay en cada fase.
- **Nodos**: el estado, los roles, las versiones, la dirección, el sistema, el
  entorno de contenedores, la capacidad, lo asignable y los taints de cada nodo.
- **Eventos**: lo que el clúster registró últimamente, lo más reciente primero.
- **Recursos de API**: cada tipo que sirve el clúster, su grupo, versión,
  alcance y verbos.

## Cuando algo se rechaza

- Un servidor de API inaccesible, un certificado no confiable, o un token o
  certificado no aceptado detiene toda la conexión, y cada pantalla dice por
  qué.
- Las reglas de acceso del propio clúster pueden rechazar una sola petición.
  Se dice como **El clúster no permite a esta conexión** con lo que se pidió,
  como `list secrets`; el resto del clúster sigue legible.

## Cambiar

El menú sobre un objeto y los iconos de la cabecera de su resumen solo ofrecen
lo que el clúster permite a tu cuenta: una acción que sus reglas de acceso
rechazarían no aparece. Escalar, reiniciar, acordonar y suspender necesitan
acceso de escritura a la conexión; eliminar, vaciar y crear objetos necesitan
acceso a la estructura.

- **Escalar** pide el número de réplicas, con el actual ya escrito, y dice el
  cambio antes de hacerlo.
- **Reiniciar** reemplaza los pods de una carga uno a uno, como
  `kubectl rollout restart`.
- **Acordonar** y **Desacordonar** impiden o permiten que lleguen pods nuevos a
  un nodo. **Vaciar** acordona el nodo y desaloja sus pods uno a uno como job
  en **Actividad**; los pods de DaemonSet y los estáticos se quedan, un pod con
  datos en `emptyDir` espera la casilla que dice que esos datos se pierden, y
  se espera a un presupuesto de interrupciones los segundos que indiques.
- **Suspender**, **Reanudar** y **Ejecutar ahora** actúan sobre un cron job;
  Ejecutar ahora inicia un job desde su plantilla, como
  `kubectl create job --from`.
- **Eliminar** deja primero que el clúster ensaye la eliminación y dice quién
  posee el objeto y lo volverá a crear; elige qué pasa con lo que posee.
- **Como YAML** abre un objeto para editarlo. Al guardar solo se envía si nadie
  lo cambió desde que lo abriste; si no, vuelve a leerlo y edítalo de nuevo. Su
  tipo, nombre y espacio de nombres no cambian. Un secreto no se edita aquí.
- **Nuevo desde YAML**, en un espacio de nombres o un tipo, toma uno o más
  objetos. El clúster ensaya cada uno primero y el formulario muestra qué se
  crearía o cambiaría, o por qué se rechaza uno; después se aplican en orden.

## Lo que Kubernetes aún no tiene aquí

- Una terminal en un contenedor, registros al día
- Métricas en un panel, búsqueda, una base de datos del clúster abierta
- Iniciar sesión en Google Kubernetes Engine con una cuenta de Google Cloud
- Los valores de un secreto, mostrados a petición
