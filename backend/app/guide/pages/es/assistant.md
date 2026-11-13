# El agente de IA

El agente responde en el espacio **IA** del interruptor de la parte superior de la barra izquierda. Trabaja a través de sus conexiones igual que usted: las enumera, encuentra y lee tablas y archivos, ejecuta consultas y acciones, abre cosas en el espacio Data, dibuja gráficos — y lee esta guía para responder preguntas sobre el propio DataPlayer. Un cambio que quiera hacer se le consulta antes.

## Antes del primer chat

El agente funciona con su propia clave de un proveedor de modelos: Anthropic, OpenAI, Google, DeepSeek y otros.

1. Abra el espacio AI y **Ajustes**.
2. Elija un modelo. El icono de llave junto a él abre la clave del proveedor: péguela, pulse **Comprobar** y guárdela. Una clave sirve para todos los modelos de ese proveedor.
3. El modelo elegido en Settings es con el que empieza un chat nuevo. Cada chat puede elegir otro en su propio cuadro de redacción.

## Un chat

- **Nuevo chat** inicia uno. Escriba en **Escribe un mensaje al agente** y pulse **Enviar**; donde el navegador puede escuchar, el micrófono dicta en su lugar.
- Mientras trabaja, los pasos del agente se muestran uno a uno: qué leyó, qué ejecutó, cuánto tardó. **Detener** termina la respuesta.
- Las respuestas son texto con formato, con tablas, gráficos y diagramas. Cada uno puede copiarse o leerse en voz alta.
- Al seleccionar palabras de una respuesta aparecen **Añadir al chat**, que las cita en su siguiente mensaje, y **Más detalles**, que pide al chat rápido que las explique.

## Lo que sabe

El agente no ve su pantalla. Para señalarle algo, use **Adjuntar pestañas o archivos**:

- **Pestañas del espacio de trabajo…**: hasta cinco pestañas abiertas — una tabla, un catálogo, una consulta, un resultado — para el siguiente mensaje;
- **Archivos del ordenador…**: archivos de texto, e imágenes PNG, JPEG, WebP o GIF para un modelo que lee imágenes.

Sin adjunto, busca cosas por nombre con la búsqueda. Cuando varias conexiones coinciden con un nombre, pregunta cuál.

## Cambios

**Cambios**, en el cuadro de redacción, indica lo que el agente puede cambiar en este chat:

- **Solo lectura**: desde este chat no se cambia nada;
- **Preguntar antes de los cambios**, con el que empieza cada chat: un cambio espera su respuesta en una tarjeta con **Allow once**, **Allow all changes in this chat** y **Permitir todos los cambios en todos los chats**. La tarjeta muestra lo que cambiaría — las sentencias, y lo que un borrado arrastraría consigo;
- **Permitir cambios**: los cambios de este chat se ejecutan sin preguntar;
- **Dejar que Jev decida**: Jev, un servicio aparte con su propia clave, decide antes de cada cambio;
- **Permitir todos los cambios en todos los chats** es un ajuste suyo, no del chat. Se desactiva de nuevo en **Ajustes**, en **Confirmaciones**.

Un chat que espera su respuesta aparece en **Requiere tu atención** en la campana de actividad. Una conexión configurada en **Solo lectura** para consolas nunca se escribe, y un nivel de acceso que usted no tiene nunca se usa.

## Qué conexiones puede leer

El agente lee una conexión solo cuando su propietario activó **Permitir el envío de datos a terceros** en la página **Permisos** de la conexión: lo que lee se envía al proveedor del modelo. Si no, el agente solo ve el nombre y el tipo de la conexión, y nada más. El propietario puede permitirlo desde el paso rechazado; a una persona con quien se comparte la conexión se le indica que pregunte al propietario.

Desactivar después este ajuste quita de las respuestas siguientes del chat lo que se leyó de esa conexión.

## Chats, proyectos y archivo

- La lista de chats tiene los **Fijados** arriba y un filtro por nombre.
- Un chat puede fijarse, moverse a un proyecto, renombrarse y archivarse.
- **Nuevo proyecto** agrupa chats. Al borrar un proyecto se pregunta si sus chats vuelven a la lista o pasan al archivo.
- **Archivo**, en Settings, restaura los chats archivados o los borra para siempre.

## Elección del modelo por Jev

En lugar de un modelo, **Elegir con Jev** deja que Jev elija uno para cada respuesta entre los modelos cuyas claves haya configurado. Su solicitud se envía a TypeSafe, el proveedor de Jev, para hacer la elección. Necesita una clave de Jev, configurada en Settings.

## Chat rápido

**Chat rápido**, arriba a la izquierda, abre una ventana para una conversación sencilla con un modelo desde cualquier espacio. No tiene herramientas y no puede leer nada de DataPlayer. En Chrome, en un ordenador de escritorio, puede responderlo Gemini Nano, que funciona en su propio ordenador una vez que Chrome lo ha descargado, así que nada sale del equipo. Los chats rápidos aparecen en el mismo historial que los chats del agente.

## Herramientas de servidores MCP externos

El agente también puede llamar a las herramientas de servidores MCP que usted añada: un gestor de incidencias, una wiki, un servicio propio.

1. Abra el espacio AI y **Ajustes**, y luego **Añadir servidor** bajo **Servidores MCP externos**.
2. Póngale un nombre y su dirección Streamable HTTP, como `https://mcp.example.com/mcp`. **Token Bearer** y **Otras cabeceras** se envían con cada solicitud; una vez guardados, nunca se vuelven a mostrar, y un campo vacío conserva lo que está configurado.
3. **Herramientas** pregunta al servidor qué ofrece. Cada herramienta indica **Lee** o **Pregunta antes**, y puede desactivarse.

- Una herramienta que no dice que solo lee se trata como un cambio: pregunta antes con los argumentos que enviaría; un chat **Solo lectura** la rechaza, y **Permitir cambios** la deja ejecutarse.
- El icono del servidor en el cuadro de redacción activa o desactiva cada servidor para ese chat.
- Un servidor que no responde se omite en esa respuesta; el resto del chat sigue.
- La lista es solo suya. Lo que el agente pasa a una herramienta sale de DataPlayer, incluidos los datos leídos de sus conexiones.
- Una dirección de esta máquina o de su red privada se rechaza, salvo que la instalación lo permita.

## Un agente de IA externo

Un agente ajeno a DataPlayer — Claude Code, Cursor, Codex y otros — puede trabajar con sus conexiones a través de la dirección MCP de DataPlayer.

1. **Preferencias**, desde el menú de usuario, y luego **Acceso MCP**.
2. **Nuevo token**: un nombre, **Solo lectura** o **Acceso completo**, y cuándo caduca. **Solo lectura** lee catálogos, filas y consultas, y rechaza todo cambio; **Acceso completo** cambia datos y ejecuta acciones sin preguntar.
3. Copie el token: solo se muestra una vez. La ventana también ofrece la línea o la entrada de archivo que configura el cliente elegido.

El agente externo tiene las mismas herramientas que este, esta guía incluida, y solo lee las conexiones cuyo propietario permite enviar datos a terceros. **Revocar este token** lo corta en su próxima llamada.

## Límites

- Una respuesta hace como máximo 50 llamadas a herramientas; más allá, haga una pregunta más concreta.
- Una lectura devuelve como máximo 20 filas cada vez.
- Un mensaje admite un número limitado de archivos de un tamaño limitado; el cuadro de redacción indica qué límite se alcanzó.
