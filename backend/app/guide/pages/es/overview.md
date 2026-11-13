# DataPlayer de un vistazo

DataPlayer conecta las fuentes con las que trabaja — bases de datos, almacenamiento de archivos, colas, servidores por SSH y otras — y le permite leerlas y cambiarlas desde un mismo lugar. Esta página indica dónde está cada cosa; cada parte tiene su propia página.

## Los cuatro espacios

El interruptor de la parte superior de la barra izquierda elige qué ocupa la pantalla:

- **Datos**: sus conexiones, sus catálogos y las tablas, archivos y consultas abiertos desde ellos. Vea [El espacio de trabajo](workspace.md) y [Conexiones](connections.md).
- **Flujos**: conexiones dispuestas en un lienzo, con enlaces que copian filas y archivos de una a otra, a mano o según un horario. Vea [Flujos](pipelines.md).
- **Cuadros de mando**: métricas que notifican los agentes y sus conexiones, dibujadas a lo largo del tiempo. Vea [Cuadros de mando](dashboards.md).
- **IA**: conversaciones con el agente, que lee y cambia sus datos por las mismas conexiones. Vea [El agente de IA](assistant.md).

Cambiar de espacio conserva lo que estaba abierto: al volver a **Datos** encuentra las mismas pestañas.

## Alrededor de la pantalla

- **La cabecera** contiene el campo de búsqueda, que encuentra conexiones, tablas, archivos, consultas guardadas, flujos, cuadros de mando, chats y páginas de esta guía. Ctrl+K (⌘K en un Mac) sitúa el cursor en él. Vea [Búsqueda](search.md).
- **El menú de usuario**, arriba a la derecha, abre **Preferencias**, **Administración** para un administrador, y **Cerrar sesión**. Vea [Preferencias y su cuenta](preferences.md).
- **Las barras** a ambos lados contienen herramientas como iconos: el interruptor de espacios y **Chat rápido** arriba a la izquierda; **Servicios**, **Terminales**, **Consultas** y **Índice de búsqueda** abajo a la izquierda; guardar y abrir grupos de pestañas arriba a la derecha. Una herramienta puede arrastrarse a otro lugar de su barra o a otra barra.
- **El panel del pie** se abre para **Servicios**, **Terminales**, **Consultas**, **Índice de búsqueda** y, para un administrador, **Registros**. Vea [Servicios y terminales](services.md).
- **La campana de actividad**, abajo a la derecha, abre **Actividad**: lo que espera su respuesta, lo que se está ejecutando y lo que ocurrió recientemente.

## Dónde leer sobre cada tema

- un tipo de fuente — su propia página: [PostgreSQL](source-postgres.md), [MySQL y MariaDB](source-mysql.md), [SQLite](source-sqlite.md), [ClickHouse](source-clickhouse.md), [Cassandra y ScyllaDB](source-cassandra.md), [MongoDB](source-mongodb.md), [Redis](source-redis.md), [ZooKeeper](source-zookeeper.md), [Kafka](source-kafka.md), [RabbitMQ](source-rabbitmq.md), [Binance](source-binance.md), [Archivos](source-file.md) y [SSH](source-ssh.md). Allí se describen, para esa fuente, la lectura y edición de filas, los cambios de estructura, la consola SQL y los informes;
- añadir, compartir y configurar una conexión — [Conexiones](connections.md);
- columnas, pestañas, ventanas y grupos de pestañas — [El espacio de trabajo](workspace.md);
- mover datos según un horario — [Flujos](pipelines.md);
- métricas y gráficos a lo largo del tiempo — [Cuadros de mando](dashboards.md);
- el agente, el chat rápido y la conexión de un agente de IA externo — [El agente de IA](assistant.md);
- servidores iniciados aquí, terminales y copias de seguridad — [Servicios y terminales](services.md).
