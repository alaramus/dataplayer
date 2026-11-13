# Búsqueda

Una sola búsqueda encuentra lo que usted puede ver en DataPlayer: las conexiones y lo que hay dentro de ellas — tablas, archivos, claves, temas — y lo que la aplicación guarda para usted: consultas guardadas, flujos, cuadros de mando, chats, servicios, claves SSH, pestañas abiertas y grupos de pestañas, tipos de fuente y páginas de esta guía.

## El campo de búsqueda

El campo de la cabecera, **Buscar en todo**, abre la búsqueda. Ctrl+K (⌘K en un Mac) hace lo mismo desde cualquier lugar salvo un terminal.

- Los resultados aparecen mientras escribe, agrupados: pestañas abiertas, conexiones, un grupo por conexión, favoritos, flujos, cuadros de mando, conversaciones, servicios, claves SSH, la guía, tipos de fuente. **Mejores coincidencias** aparecen primero.
- Un nombre coincide cuando contiene cada palabra escrita, en cualquier orden y sin distinguir mayúsculas. Un nombre exacto, o que empieza por su primera palabra, aparece por encima de uno que solo contiene las palabras.
- Mientras escribe, no se consulta a los lugares lentos. **Enter** busca en todo, esperando a cada conexión todo el tiempo que sea necesario.
- Cada lugar indica lo que le ocurrió: no se encontró nada, no respondió a tiempo, no se puede acceder, está desactivado, está bloqueado. Algunos ofrecen un gesto — **Intentar de nuevo**, **Buscar de todos modos**, **Desbloquear la clave SSH**.
- **Preguntar al agente**, al final de la lista, abre un chat nuevo con sus palabras, todavía sin enviar.
- Un campo vacío muestra las búsquedas recientes y lo que abrió hace poco.

Pulsar un resultado lo abre donde vive: una tabla en el espacio de trabajo, un flujo en Pipelines, un chat en el espacio AI, una página de la guía en la ventana de la guía. **Mostrar en el catálogo** encuentra en cambio una tabla o un archivo en su catálogo.

## Buscar en una conexión

Abierta mientras un catálogo tiene el foco, la búsqueda ofrece primero **Buscar en ‹conexión›**: la flecha derecha lo acepta, Backspace lo quita. El filtro del catálogo hace lo mismo para un nivel, y su botón de búsqueda para todo lo que hay debajo.

## La pestaña Search

**Mostrar todos los resultados**, o Enter, abre la pestaña **Buscar** en la columna de trabajo. Contiene la respuesta completa y la filtra por grupo, conexión, tipo y la fecha en que algo cambió.

**Buscar dentro de archivos** lee el texto de cada archivo bajo las conexiones que marque. Puede tardar minutos, omite los archivos binarios y los de más de 8 MB (1 MB por SSH), y se ejecuta en segundo plano; lo que encuentra llega según avanza, y **Detener** conserva lo encontrado hasta entonces.

## El índice de búsqueda

Una conexión con muchos nombres responde despacio cuando se le pregunta cada vez. Su propietario puede guardar una lista de sus nombres en este servidor: **Índice de búsqueda…** en el menú de acciones del catálogo, la herramienta **Índice de búsqueda** de la barra izquierda inferior, o la página **Opciones** de la ventana de la conexión.

- **Conservar una lista de nombres para la búsqueda** copia los nombres de tablas, claves, carpetas y archivos a la base de datos de este servidor como texto plano, leídos con las credenciales del propietario. Desactivarlo borra la copia.
- **Volver a leer dentro de** — 1 hora, 6 horas, 1 día o 1 semana — indica cuánta antigüedad puede tener la lista antes de que la búsqueda pregunte a la fuente. **Leer ahora** la vuelve a leer de inmediato.
- **Lo que contienen los archivos**, para una carpeta, guarda también el texto de los archivos que contiene, de modo que una palabra dentro de ellos se encuentra con Enter sin volver a abrirlos.
- Solo el propietario lo activa; una persona con quien se comparte la conexión ve el estado.

Donde este servidor ejecuta el modelo para ello, una lista guardada también se busca por significado: con Enter, las filas marcadas **Por significado** añaden lo que solo las palabras no encontraron.
