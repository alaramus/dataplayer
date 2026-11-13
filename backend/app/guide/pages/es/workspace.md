# El espacio de trabajo

El espacio **Datos** es donde se abren las conexiones y se leen sus contenidos. Lo que son los demás espacios está en [DataPlayer de un vistazo](overview.md).

## Tres columnas

- **Conexiones**, a la izquierda: todas las conexiones que le pertenecen o que se compartieron con usted. Al pulsar una se abre su catálogo. Vea [Conexiones](connections.md).
- **Catalogs**, en el centro: lo que contiene cada conexión abierta, nivel por nivel. El filtro de arriba reduce el nivel por nombre; su botón de búsqueda busca un nombre en todo lo que hay debajo. **Duplicar el catálogo junto a este** abre una segunda copia del mismo catálogo.
- **Work**, a la derecha: las tablas, archivos, consultas, estructuras y gráficos abiertos desde un catálogo, cada uno en una pestaña. Mientras está vacía, indica qué hacer a continuación.

Las columnas se redimensionan arrastrando la línea que las separa. La disposición que deja es la que encuentra la próxima vez.

## Pestañas

- Una pestaña se arrastra como una pestaña del navegador: si se suelta sobre las pestañas de otra columna, se une a ellas; si se suelta en el cuerpo de una columna, la divide en dos. Una pestaña solo puede ir a una columna que acepte su tipo.
- **Mostrar en el catálogo** encuentra el nodo de una pestaña en su catálogo.
- **Abrir en una ventana** saca una pestaña a una ventana flotante, y **Abrir como pestaña** la devuelve.
- **Cerrar las demás pestañas**, un botón al final de las pestañas de una columna, cierra todas excepto la que se muestra.
- La marca junto a un botón de recargar dice **En vivo** cuando lo mostrado acaba de leerse de la fuente, y un reloj cuando es una respuesta guardada. Al apuntar a ella se indica su antigüedad.

Una parte de la disposición puede apartarse: sale de la pantalla y espera como un botón en **Secciones apartadas**, al pie, que la devuelve.

## Grupos de pestañas

Las pestañas abiertas en Data y la disposición de las columnas pueden guardarse con un nombre.

- **Guardar grupo**, en la barra derecha superior, guarda lo que está abierto ahora.
- **Grupos de pestañas guardados**, junto a él, los muestra. Abrir uno reemplaza las pestañas abiertas y pide confirmación antes.
- **Gestionar grupo** renombra un grupo, lo borra o lo actualiza con la disposición actual. Borrar un grupo no cierra ninguna pestaña.

## Ventanas flotantes

Los ajustes de una conexión, los formularios, las preguntas y las pestañas sacadas se abren en ventanas flotantes, y puede haber varias a la vez. Nada en DataPlayer bloquea el resto de la pantalla.

- Una ventana se mueve por su barra, se redimensiona por sus bordes, y tiene **Minimizar**, **Maximizar** y **Cerrar ventana**.
- Una ventana con un formulario solo se cierra con su cruz, para que pulsar Esc no pierda lo escrito. Una pregunta se cierra también con Esc.
- Una ventana minimizada espera en **Ventanas abiertas**, al pie de la pantalla.

## Dos conexiones una junto a otra

**Emparejar con otra conexión**, en la cabecera de un catálogo, pone los catálogos de dos conexiones en una misma ventana, para mover cosas entre ellas: indica qué puede pasar de una a otra, y **Cambiar de lado** invierte el sentido. **Olvidar este par** cierra el par.

## Actividad y notificaciones

La campana de actividad, abajo a la derecha, abre **Actividad**, con tres secciones:

- **Requiere tu atención**: lo que espera su respuesta — una pregunta de un agente, alguien que pide acceso a su conexión, una conexión que dejó de responder, una tarea que falló;
- **Trabajando**: lo que el servidor hace por usted — copias, copias de seguridad, ejecuciones de flujos, arranque de servicios, búsquedas dentro de archivos. El trabajo largo puede pausarse o detenerse aquí cuando lo permite;
- **Reciente**: lo que se dijo hace poco. **Borrar todo** lo vacía.

Los avisos breves aparecen como tarjetas abajo a la derecha y pasan a **Reciente**. **No molestar** detiene las tarjetas; todo sigue en Activity.
