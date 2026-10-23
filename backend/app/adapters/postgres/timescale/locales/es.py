"""Lo que escriben las acciones e informes de TimescaleDB, en español (D226).

Los términos siguen el glosario de las pantallas; los nombres de funciones y
opciones propios de TimescaleDB se dejan como están.
"""

MESSAGES: dict[str, str] = {
    # Longitudes, tal como las muestra una vista previa.
    "{amount} second": "{amount} s",
    "{amount} seconds": "{amount} s",
    "{amount} minute": "{amount} sin",
    "{amount} minutes": "{amount} sin",
    "{amount} hour": "{amount} h",
    "{amount} hours": "{amount} h",
    "{amount} day": "{amount} d",
    "{amount} days": "{amount} d",
    "{amount} week": "{amount} Sem",
    "{amount} weeks": "{amount} Sem",
    "{amount} month": "{amount} mes",
    "{amount} months": "{amount} meses",
    "{amount} year": "{amount} año",
    "{amount} years": "{amount} años",
    "{amount} value": "{amount} valor",
    "{amount} values": "{amount} valores",
    # Informes.
    "Hypertables": "Hipertablas",
    "Hypertable owners, dimension/chunk counts and compression configuration": (
        "Propietarios de hipertablas, número de dimensiones y fragmentos, y configuración de compresión"
    ),
    "Continuous aggregates": "Agregados continuos",
    "Aggregate owners, source/materialization identities and configuration": (
        "Propietarios de agregados, identidades de origen y materialización, y configuración"
    ),
    "Chunks": "Fragmentos",
    "Chunk identities, primary-dimension boundaries and compression status": (
        "Identidades de fragmentos, límites de la dimensión principal y estado de compresión"
    ),
    "Dimensions": "Dimensiones",
    "Time, integer and space dimensions of each hypertable": (
        "Dimensiones temporales, enteras y espaciales de cada hipertabla"
    ),
    "Policies and jobs": "Políticas y tareas",
    "Native TimescaleDB jobs, including policies and their schedules": (
        "Tareas nativas de TimescaleDB, incluidas las políticas y sus programaciones"
    ),
    "Job statistics": "Estadísticas de tareas",
    "Recorded native job runs, outcomes and counters; unrun jobs may be absent": (
        "Ejecuciones registradas de tareas nativas, sus resultados y contadores; las tareas que aún no se han "
        "ejecutado pueden faltar"
    ),
    "Detached chunks": "Fragmentos separados",
    "Tables named like a chunk that no hypertable holds; Attach chunk takes one back": (
        "Tablas con nombre de fragmento que no pertenecen a ninguna hipertabla; «Adjuntar tabla como fragmento» "
        "las recupera"
    ),
    "This report cannot be inspected by this connection": "Esta conexión no puede inspeccionar este informe",
    "The installed TimescaleDB lacks the public API for this view": (
        "La versión instalada de TimescaleDB no tiene la API pública para esta vista"
    ),
    # Descubrir TimescaleDB.
    "TimescaleDB is not installed on this database": "TimescaleDB no está instalado en esta base de datos",
    "This source has no usable TimescaleDB API": "Esta fuente no tiene una API de TimescaleDB utilizable",
    "This connection may not inspect installed extensions": (
        "Esta conexión no puede inspeccionar las extensiones instaladas"
    ),
    "Installed extensions could not be inspected": "No se pudieron inspeccionar las extensiones instaladas",
    "The installed TimescaleDB version could not be read": "No se pudo leer la versión instalada de TimescaleDB",
    "TimescaleDB extension metadata could not be read": (
        "No se pudieron leer los metadatos de la extensión TimescaleDB"
    ),
    "This TimescaleDB major version is not supported": "Esta versión mayor de TimescaleDB no es compatible",
    "This connection may not inspect TimescaleDB metadata": (
        "Esta conexión no puede inspeccionar los metadatos de TimescaleDB"
    ),
    "TimescaleDB metadata could not be inspected": "No se pudieron inspeccionar los metadatos de TimescaleDB",
    "The installed version lacks the supported inspection API": (
        "La versión instalada no tiene la API de inspección compatible"
    ),
    "TimescaleDB action vocabulary could not be inspected": (
        "No se pudo determinar qué acciones de TimescaleDB están disponibles"
    ),
    "The TimescaleDB {routine} API is not usable by this connection": (
        "Esta conexión no puede usar la API {routine} de TimescaleDB"
    ),
    "The TimescaleDB {type} type is not usable by this connection": (
        "Esta conexión no puede usar el tipo {type} de TimescaleDB"
    ),
    "This connection may not lock TimescaleDB public metadata": (
        "Esta conexión no puede bloquear los metadatos públicos de TimescaleDB"
    ),
    # Datos de TimescaleDB de una relación.
    "TimescaleDB metadata no longer identifies this relation uniquely": (
        "Los metadatos de TimescaleDB ya no identifican esta relación de forma única"
    ),
    "TimescaleDB metadata inspection timed out": "Se agotó el tiempo para inspeccionar los metadatos de TimescaleDB",
    "TimescaleDB metadata could not be inspected safely": (
        "No se pudieron inspeccionar los metadatos de TimescaleDB de forma segura"
    ),
    "TimescaleDB size inspection timed out": "Se agotó el tiempo para determinar el tamaño en TimescaleDB",
    "TimescaleDB compression inspection timed out": (
        "Se agotó el tiempo para leer las estadísticas de compresión de TimescaleDB"
    ),
    "TimescaleDB size could not be inspected safely": (
        "No se pudo determinar el tamaño en TimescaleDB de forma segura"
    ),
    "TimescaleDB compression statistics could not be inspected safely": (
        "No se pudieron leer las estadísticas de compresión de TimescaleDB de forma segura"
    ),
    # Qué tablas toma una acción.
    "Choose one user hypertable": "Elija una hipertabla de usuario",
    "Choose one user continuous aggregate": "Elija un agregado continuo de usuario",
    "Choose an owned hypertable": "Elija una hipertabla de la que sea propietario",
    "Choose an owned hypertable with one time dimension": (
        "Elija una hipertabla de la que sea propietario con una dimensión temporal"
    ),
    "Choose an owned hypertable partitioned by time": (
        "Elija una hipertabla de la que sea propietario, particionada por tiempo"
    ),
    "Choose an owned continuous aggregate": "Elija un agregado continuo del que sea propietario",
    "Only timestamp and date dimensions are supported here": (
        "Aquí solo se admiten dimensiones de tipo timestamp y date"
    ),
    "Only a hypertable with one range dimension is maintained here": (
        "Aquí solo se mantienen hipertablas con una dimensión de rango"
    ),
    "Only timestamp, date and integer dimensions are supported here": (
        "Aquí solo se admiten dimensiones de tipo timestamp, date y enteras"
    ),
    "Only aggregates over timestamp and date dimensions are supported here": (
        "Aquí solo se admiten agregados sobre dimensiones de tipo timestamp y date"
    ),
    # Revisar y aplicar un plan.
    "The operation plan changed; review it again": "El plan de la operación cambió; revíselo de nuevo",
    "Validation timed out; review the plan again": "Se agotó el tiempo de validación; revise el plan de nuevo",
    "The source changed or is busy; review the plan again": (
        "La fuente cambió o está ocupada; revise el plan de nuevo"
    ),
    "The change could not be confirmed; reload the source before reviewing again": (
        "No se pudo confirmar el cambio; vuelva a cargar la fuente antes de revisar de nuevo"
    ),
    "The change ran past its {seconds} seconds and was rolled back": (
        "El cambio superó sus {seconds} segundos y se revirtió"
    ),
    "This connection may not make this change or lock its metadata": (
        "Esta conexión no puede hacer este cambio ni bloquear sus metadatos"
    ),
    "The source refused the change": "La fuente rechazó el cambio",
    "Runs in Activity, one such job per connection at a time; access is checked again before every chunk": (
        "Se ejecuta en Actividad, una tarea de este tipo por conexión a la vez; el acceso se comprueba de nuevo "
        "antes de cada fragmento"
    ),
    "Runs in Activity, one such job per connection at a time; access is checked again before every unit": (
        "Se ejecuta en Actividad, una tarea de este tipo por conexión a la vez; el acceso se comprueba de nuevo "
        "antes de cada paso"
    ),
    # Líneas compartidas de una vista previa.
    "Time dimension: {column}": "Dimensión temporal: {column}",
    "Unit": "Unidad",
    "{chunk}: {start} to {end}": "{chunk}: de {start} a {end}",
    "…and {count} more": "…y {count} más",
    "Whole chunks from the earliest chunk to {end}": "Fragmentos completos desde el más antiguo hasta {end}",
    "Whole chunks from {start} to {end}": "Fragmentos completos de {start} a {end}",
    "Give an instant with its time zone, such as 2026-01-15T00:00:00Z, or a whole number": (
        "Indique un instante con su zona horaria, como 2026-01-15T00:00:00Z, o un número entero"
    ),
    "The number is outside the range of a bigint": "El número está fuera del rango de un bigint",
    "Both ends are instants, or both are numbers": "Ambos extremos deben ser instantes o ambos deben ser números",
    "The range must start before it ends": "El inicio del rango debe ser anterior a su fin",
    "The window must start before it ends": "El inicio de la ventana debe ser anterior a su fin",
    "Chunks ending at or before": "Fragmentos que terminan en o antes de",
    "With its time zone; only chunks lying entirely inside the window are chosen": (
        "Con su zona horaria; solo se eligen los fragmentos que están completamente dentro de la ventana"
    ),
    "and starting at or after": "y que empiezan en o después de",
    "Leave empty for every earlier chunk": "Déjelo vacío para todos los fragmentos anteriores",
    # Intervalo de fragmentos.
    "Change chunk interval": "Cambiar el intervalo de fragmentos",
    "Review the interval plan before applying it": "Revise el plan del intervalo antes de aplicarlo",
    "Future chunk interval changed; existing chunks were not repartitioned": (
        "Se cambió el intervalo de los fragmentos futuros; los fragmentos existentes no se reparticionaron"
    ),
    "Change the future chunk interval for {target}": "Cambiar el intervalo de los fragmentos futuros de {target}",
    "Current interval: {interval}": "Intervalo actual: {interval}",
    "Requested interval: {interval}": "Intervalo solicitado: {interval}",
    "Only future chunks use the new interval; existing chunks are not repartitioned": (
        "Solo los fragmentos futuros usan el nuevo intervalo; los fragmentos existentes no se reparticionan"
    ),
    "Briefly locks TimescaleDB metadata across this database; new chunk creation may wait": (
        "Bloquea brevemente los metadatos de TimescaleDB en toda esta base de datos; la creación de nuevos "
        "fragmentos puede esperar"
    ),
    "TimescaleDB interval metadata could not be inspected safely": (
        "No se pudieron leer los metadatos del intervalo de TimescaleDB de forma segura"
    ),
    "TimescaleDB interval planning timed out": "Se agotó el tiempo para planificar el intervalo de TimescaleDB",
    "Calendar chunk intervals are not supported by this strategy": (
        "Esta estrategia no admite intervalos de fragmentos de calendario"
    ),
    "Date dimensions require whole days or weeks": "Las dimensiones de tipo date requieren días o semanas completos",
    "Interval validation timed out; review the plan again": (
        "Se agotó el tiempo de validación del intervalo; revise el plan de nuevo"
    ),
    "This connection may not change the interval or lock its metadata": (
        "Esta conexión no puede cambiar el intervalo ni bloquear sus metadatos"
    ),
    "The source refused the interval change": "La fuente rechazó el cambio de intervalo",
    "The interval change could not be confirmed; reload the source before reviewing again": (
        "No se pudo confirmar el cambio de intervalo; vuelva a cargar la fuente antes de revisar de nuevo"
    ),
    # Políticas de retención y compresión.
    "Set retention policy": "Establecer política de retención",
    "Remove retention policy": "Eliminar política de retención",
    "Set compression policy": "Establecer política de compresión",
    "Remove compression policy": "Eliminar política de compresión",
    "TimescaleDB will keep dropping old chunks by itself, even after this session ends. Set this policy?": (
        "TimescaleDB seguirá eliminando fragmentos antiguos por sí solo, incluso después de que termine esta "
        "sesión. ¿Establecer esta política?"
    ),
    "Drop chunks older than": "Eliminar fragmentos anteriores a",
    "Compress chunks older than": "Comprimir fragmentos anteriores a",
    "Set the retention policy for {target}": "Establecer la política de retención de {target}",
    "Remove the retention policy from {target}": "Eliminar la política de retención de {target}",
    "Set the compression policy for {target}": "Establecer la política de compresión de {target}",
    "Remove the compression policy from {target}": "Eliminar la política de compresión de {target}",
    "No retention policy exists yet": "Todavía no hay política de retención",
    "No compression policy exists yet": "Todavía no hay política de compresión",
    "older than {age}": "anteriores a {age}",
    "created more than {age} ago": "creados hace más de {age}",
    "Removes job {job}, which drops chunks {chunks}": "Elimina la tarea {job}, que elimina los fragmentos {chunks}",
    "Replaces job {job}, which drops chunks {chunks}": "Reemplaza la tarea {job}, que elimina los fragmentos {chunks}",
    "Removes job {job}, which compresses chunks {chunks}": (
        "Elimina la tarea {job}, que comprime los fragmentos {chunks}"
    ),
    "Replaces job {job}, which compresses chunks {chunks}": (
        "Reemplaza la tarea {job}, que comprime los fragmentos {chunks}"
    ),
    "The current policy runs every {every}; its replacement uses TimescaleDB's default schedule": (
        "La política actual se ejecuta cada {every}; su reemplazo usará la programación predeterminada de TimescaleDB"
    ),
    "New policy: drop chunks older than {age}": "Nueva política: eliminar fragmentos anteriores a {age}",
    "New policy: compress chunks older than {age}": "Nueva política: comprimir fragmentos anteriores a {age}",
    "TimescaleDB keeps dropping whole chunks older than this on its own schedule, after this session ends": (
        "TimescaleDB seguirá eliminando fragmentos completos anteriores a este valor según su propia "
        "programación, después de que termine esta sesión"
    ),
    "TimescaleDB stops dropping old chunks automatically; chunks already dropped do not return": (
        "TimescaleDB dejará de eliminar fragmentos antiguos automáticamente; los fragmentos ya eliminados no "
        "vuelven"
    ),
    "TimescaleDB keeps compressing chunks older than this on its own schedule; compressed chunks stay readable": (
        "TimescaleDB seguirá comprimiendo fragmentos anteriores a este valor según su propia programación; los "
        "fragmentos comprimidos siguen siendo legibles"
    ),
    "TimescaleDB stops compressing chunks automatically; chunks already compressed stay compressed": (
        "TimescaleDB dejará de comprimir fragmentos automáticamente; los fragmentos ya comprimidos seguirán "
        "comprimidos"
    ),
    "Other policy changes made here in this database wait until it commits, and so may a policy run starting meanwhile": (
        "Otros cambios de políticas realizados aquí en esta base de datos esperan a que se confirme, y también "
        "puede hacerlo una ejecución de política que empiece mientras tanto"
    ),
    "Review the retention policy plan before applying it": (
        "Revise el plan de la política de retención antes de aplicarlo"
    ),
    "Review the compression policy plan before applying it": (
        "Revise el plan de la política de compresión antes de aplicarlo"
    ),
    "Retention policy set: TimescaleDB drops chunks older than {age} on its own schedule": (
        "Política de retención establecida: TimescaleDB elimina fragmentos anteriores a {age} según su propia programación"
    ),
    "Retention policy removed; TimescaleDB no longer drops old chunks automatically": (
        "Política de retención eliminada; TimescaleDB ya no elimina fragmentos antiguos automáticamente"
    ),
    "Compression policy set: TimescaleDB compresses chunks older than {age} on its own schedule": (
        "Política de compresión establecida: TimescaleDB comprime fragmentos anteriores a {age} según su propia programación"
    ),
    "Compression policy removed; TimescaleDB no longer compresses chunks automatically": (
        "Política de compresión eliminada; TimescaleDB ya no comprime fragmentos automáticamente"
    ),
    "This hypertable has several retention policy jobs; manage them with SQL": (
        "Esta hipertabla tiene varias tareas de política de retención; gestiónelas con SQL"
    ),
    "This hypertable has several compression policy jobs; manage them with SQL": (
        "Esta hipertabla tiene varias tareas de política de compresión; gestiónelas con SQL"
    ),
    "The existing retention policy could not be read safely; manage it with SQL": (
        "No se pudo leer la política de retención actual de forma segura; gestiónela con SQL"
    ),
    "The existing compression policy could not be read safely; manage it with SQL": (
        "No se pudo leer la política de compresión actual de forma segura; gestiónela con SQL"
    ),
    "TimescaleDB retention policy planning timed out": (
        "Se agotó el tiempo para planificar la política de retención de TimescaleDB"
    ),
    "TimescaleDB compression policy planning timed out": (
        "Se agotó el tiempo para planificar la política de compresión de TimescaleDB"
    ),
    "TimescaleDB retention policy metadata could not be inspected safely": (
        "No se pudieron leer los metadatos de la política de retención de TimescaleDB de forma segura"
    ),
    "TimescaleDB compression policy metadata could not be inspected safely": (
        "No se pudieron leer los metadatos de la política de compresión de TimescaleDB de forma segura"
    ),
    "Enable compression on this hypertable first": "Active primero la compresión en esta hipertabla",
    "This hypertable has no retention policy": "Esta hipertabla no tiene política de retención",
    "This hypertable has no compression policy": "Esta hipertabla no tiene política de compresión",
    "Date dimensions require whole days, weeks, months or years": (
        "Las dimensiones de tipo date requieren días, semanas, meses o años completos"
    ),
    "The existing retention policy is paused; remove it before setting a new one": (
        "La política de retención actual está en pausa; elimínela antes de establecer una nueva"
    ),
    "The existing compression policy is paused; remove it before setting a new one": (
        "La política de compresión actual está en pausa; elimínela antes de establecer una nueva"
    ),
    # Políticas de actualización de agregados continuos.
    "Set refresh policy": "Establecer política de actualización",
    "Remove refresh policy": "Eliminar política de actualización",
    "Window starts": "Inicio de la ventana",
    "How long ago the refreshed window begins": "Hace cuánto empieza la ventana que se actualiza",
    "Window ends": "Fin de la ventana",
    "How long ago it ends; more recent than the start": "Hace cuánto termina; más reciente que el inicio",
    "Refresh every": "Actualizar cada",
    "Set the refresh policy for {target}": "Establecer la política de actualización de {target}",
    "Remove the refresh policy from {target}": "Eliminar la política de actualización de {target}",
    "Source hypertable: {source}": "Hipertabla de origen: {source}",
    "No refresh policy exists yet": "Todavía no hay política de actualización",
    "from the earliest data to the latest data": "desde los datos más antiguos hasta los más recientes",
    "from the earliest data to {end} ago": "desde los datos más antiguos hasta hace {end}",
    "from {start} ago to the latest data": "desde hace {start} hasta los datos más recientes",
    "from {start} ago to {end} ago": "desde hace {start} hasta hace {end}",
    "Removes job {job}, which refreshes {window} every {every}": (
        "Elimina la tarea {job}, que actualiza {window} cada {every}"
    ),
    "Replaces job {job}, which refreshes {window} every {every}": (
        "Reemplaza la tarea {job}, que actualiza {window} cada {every}"
    ),
    "New policy: refresh from {start} ago to {end} ago, every {every}": (
        "Nueva política: actualizar desde hace {start} hasta hace {end}, cada {every}"
    ),
    "The source hypertable has no retention policy": "La hipertabla de origen no tiene política de retención",
    "The source drops chunks older than {age}; the window starts after that": (
        "La fuente elimina fragmentos anteriores a {age}; la ventana empieza después"
    ),
    "The source drops chunks {chunks}; check that it keeps the raw data this window refreshes": (
        "La fuente elimina fragmentos {chunks}; compruebe que conserva los datos sin procesar que actualiza esta ventana"
    ),
    "TimescaleDB stops refreshing this aggregate automatically; its materialized rows stay as they are": (
        "TimescaleDB dejará de actualizar este agregado automáticamente; sus filas materializadas permanecerán "
        "como están"
    ),
    "TimescaleDB keeps refreshing this window on its own schedule, after this session ends": (
        "TimescaleDB seguirá actualizando esta ventana según su propia programación, después de que termine "
        "esta sesión"
    ),
    "This continuous aggregate has no refresh policy": "Este agregado continuo no tiene política de actualización",
    "Review the refresh policy plan before applying it": (
        "Revise el plan de la política de actualización antes de aplicarlo"
    ),
    "Refresh policy set: TimescaleDB refreshes this aggregate on its own schedule": (
        "Política de actualización establecida: TimescaleDB actualiza este agregado según su propia programación"
    ),
    "Refresh policy removed; TimescaleDB no longer refreshes this aggregate automatically": (
        "Política de actualización eliminada; TimescaleDB ya no actualiza este agregado automáticamente"
    ),
    "The existing refresh policy is paused; remove it before setting a new one": (
        "La política de actualización actual está en pausa; elimínela antes de establecer una nueva"
    ),
    "TimescaleDB refresh policy planning timed out": (
        "Se agotó el tiempo para planificar la política de actualización de TimescaleDB"
    ),
    "TimescaleDB refresh policy metadata could not be inspected safely": (
        "No se pudieron leer los metadatos de la política de actualización de TimescaleDB de forma segura"
    ),
    "This continuous aggregate has several refresh policy jobs; manage them with SQL": (
        "Este agregado continuo tiene varias tareas de política de actualización; gestiónelas con SQL"
    ),
    "The existing refresh policy could not be read safely; manage it with SQL": (
        "No se pudo leer la política de actualización actual de forma segura; gestiónela con SQL"
    ),
    "Date dimensions require offsets in whole days, weeks, months or years": (
        "Las dimensiones de tipo date requieren desplazamientos en días, semanas, meses o años completos"
    ),
    "The window must start further back than it ends": (
        "El inicio de la ventana debe estar más atrás en el pasado que su fin"
    ),
    "The window reaches data the source's retention policy drops (older than {age}); refreshing there would remove aggregated rows": (
        "La ventana alcanza datos que elimina la política de retención de la fuente (anteriores a {age}); actualizar ahí eliminaría filas agregadas"
    ),
    # Ajustes de compresión.
    "Configure compression": "Configurar compresión",
    "Segment by": "Segmentar por",
    "One column per line; leave empty for none": "Una columna por línea; déjelo vacío para no especificar ninguna",
    "Order by": "Ordenar por",
    "One column per line, optionally followed by ASC or DESC and NULLS FIRST or NULLS LAST; the time column is added descending when neither list names it": (
        "Una columna por línea, opcionalmente seguida de ASC o DESC y NULLS FIRST o NULLS LAST; si ninguna lista nombra la columna de tiempo, se añade en orden descendente"
    ),
    "TimescaleDB compression settings could not be inspected safely": (
        "No se pudieron leer los ajustes de compresión de TimescaleDB de forma segura"
    ),
    "Change the compression settings of {target}": "Cambiar los ajustes de compresión de {target}",
    "Enable compression on {target}": "Activar la compresión en {target}",
    "Current segment by: {columns}": "Segmentación actual: {columns}",
    "Current segment by: none": "Segmentación actual: ninguna",
    "Current order by: {columns}": "Orden actual: {columns}",
    "Current order by: none": "Orden actual: ninguno",
    "Compression is not enabled yet": "La compresión aún no está activada",
    "New segment by: {columns}": "Nueva segmentación: {columns}",
    "New segment by: none": "Nueva segmentación: ninguna",
    "New order by: {columns}": "Nuevo orden: {columns}",
    "Already compressed chunks keep the settings they were compressed with": (
        "Los fragmentos ya comprimidos conservan los ajustes con los que se comprimieron"
    ),
    "TimescaleDB recommends segmenting or ordering by the unique column {column}": (
        "TimescaleDB recomienda segmentar u ordenar por la columna única {column}"
    ),
    "Review the compression settings plan before applying it": (
        "Revise el plan de ajustes de compresión antes de aplicarlo"
    ),
    "Compression settings changed; only chunks compressed from now on use them": (
        "Se cambiaron los ajustes de compresión; solo los fragmentos comprimidos a partir de ahora los usan"
    ),
    "Compression enabled; chunks are compressed by a compression policy or on request": (
        "Compresión activada; los fragmentos se comprimen mediante una política de compresión o a petición"
    ),
    "Nothing is compressed now; chunks are compressed later by a compression policy or on request": (
        "Ahora no se comprime nada; los fragmentos se comprimirán más adelante mediante una política de "
        "compresión o a petición"
    ),
    "Only chunks compressed from now on use these settings; already compressed chunks keep theirs": (
        "Solo los fragmentos comprimidos a partir de ahora usan estos ajustes; los ya comprimidos conservan los "
        "suyos"
    ),
    "Locks this hypertable exclusively while the settings change; its reads and writes wait until it commits": (
        "Bloquea esta hipertabla en exclusiva mientras cambian los ajustes; sus lecturas y escrituras esperan a "
        "que se confirme"
    ),
    "Column \"{column}\" is listed more than once": "La columna «{column}» aparece más de una vez",
    "List at most {count} segment-by columns": "Indique como máximo {count} columnas de segmentación",
    "List at most {count} order-by columns": "Indique como máximo {count} columnas de orden",
    "Each line names one column": "Cada línea debe nombrar una columna",
    "This hypertable has no column \"{column}\"": "Esta hipertabla no tiene la columna «{column}»",
    "The current compression settings could not be read": "No se pudieron leer los ajustes de compresión actuales",
    "TimescaleDB compression settings planning timed out": (
        "Se agotó el tiempo para planificar los ajustes de compresión de TimescaleDB"
    ),
    # Convertir una tabla.
    "Convert to hypertable": "Convertir en hipertabla",
    "The table becomes a hypertable, which DataPlayer cannot turn back into an ordinary table. Convert it?": (
        "La tabla se convertirá en una hipertabla y DataPlayer no podrá volver a convertirla en una tabla normal. ¿Convertirla?"
    ),
    "Time column": "Columna de tiempo",
    "A timestamp or date column of this table": "Una columna de esta tabla de tipo timestamp o date",
    "Chunk interval": "Intervalo de fragmentos",
    "The table could not be inspected safely for conversion": (
        "No se pudo inspeccionar la tabla de forma segura antes de la conversión"
    ),
    "Convert {target} into a hypertable": "Convertir {target} en una hipertabla",
    "Time column: {column} ({type})": "Columna de tiempo: {column} ({type})",
    "Chunk interval: {interval}": "Intervalo de fragmentos: {interval}",
    "The table is empty, and the conversion refuses if a row arrives before it runs": (
        "La tabla está vacía y la conversión se rechaza si llega una fila antes de que se ejecute"
    ),
    "{column} becomes NOT NULL": "{column} pasa a ser NOT NULL",
    "{column} becomes NOT NULL; a row without a time makes the conversion fail and roll back": (
        "{column} pasa a ser NOT NULL; una fila sin tiempo hará que la conversión falle y se revierta"
    ),
    "An index on {column} alone already exists, so TimescaleDB adds none": (
        "Ya existe un índice solo sobre {column}, así que TimescaleDB no añadirá ninguno"
    ),
    "TimescaleDB adds an index on {column}, newest first": (
        "TimescaleDB añadirá un índice sobre {column}, con los más recientes primero"
    ),
    "The table keeps its name and identity and becomes a hypertable; DataPlayer cannot turn it back into an ordinary table": (
        "La tabla conserva su nombre e identidad y se convierte en una hipertabla; DataPlayer no podrá volver a convertirla en una tabla normal"
    ),
    "Locks this table exclusively for the conversion; its reads and writes wait until it commits": (
        "Bloquea esta tabla en exclusiva durante la conversión; sus lecturas y escrituras esperan a que se "
        "confirme"
    ),
    "Review the conversion plan before applying it": "Revise el plan de conversión antes de aplicarlo",
    "Converted to a hypertable; rows added from now on are stored in chunks": (
        "Convertida en hipertabla; las filas añadidas a partir de ahora se almacenan en fragmentos"
    ),
    "Choose an existing ordinary table": "Elija una tabla normal existente",
    "This table is already a hypertable": "Esta tabla ya es una hipertabla",
    "Foreign keys between this table and a hypertable are not supported": (
        "No se admiten claves externas entre esta tabla y una hipertabla"
    ),
    "This table has no timestamp or date column to partition by": (
        "Esta tabla no tiene ninguna columna de tipo timestamp o date por la que participar"
    ),
    "This table has no timestamp, date or integer column to partition by": (
        "Esta tabla no tiene ninguna columna de tipo timestamp, date o entera por la que participar"
    ),
    "This table is not empty; only empty tables are converted here": (
        "Esta tabla no está vacía; aquí solo se convierten tablas vacías"
    ),
    "This table has too many indexes to inspect": "Esta tabla tiene demasiados índices para inspeccionarla",
    "The TimescaleDB conversion API is split across schemas": (
        "La API de conversión de TimescaleDB está repartida entre varios esquemas"
    ),
    "TimescaleDB conversion planning timed out": "Se agotó el tiempo para planificar la conversión de TimescaleDB",
    "Only the table's owner can convert it": "Solo el propietario de la tabla puede convertirla",
    "This connection may not read the table": "Esta conexión no puede leer esta tabla",
    "Partitioned tables cannot become hypertables": "Las tablas particionadas no pueden convertirse en hipertablas",
    "Choose an ordinary table": "Elija una tabla normal",
    "Tables with NO INHERIT constraints cannot become hypertables": (
        "Las tablas con restricciones NO INHERIT no pueden convertirse en hipertablas"
    ),
    "Tables that use inheritance cannot become hypertables": (
        "Las tablas que usan herencia no pueden convertirse en hipertablas"
    ),
    "Only logged tables can become hypertables": "Solo las tablas logré pueden convertirse en hipertablas",
    "Tables with rules cannot become hypertables": "Las tablas con reglas no pueden convertirse en hipertablas",
    "Choose a column this table can be partitioned by: {choices}": (
        "Elija una columna por la que se pueda participar esta tabla: {choices}"
    ),
    "Unique index \"{index}\" must include \"{column}\", which partitions the table": (
        "El índice único «{index}» debe incluir «{column}», que particiona la tabla"
    ),
    "An integer or UUID column is converted from Hypertable settings": (
        "Una columna entera o UUID se convierte desde la ventana «Ajustes de hipertabla»"
    ),
    "Date columns require whole days or weeks": "Las columnas de tipo date requieren días o semanas completos",
    # Comprimir y descomprimir fragmentos.
    "Compress chunks": "Comprimir fragmentos",
    "Decompress chunks": "Descomprimir fragmentos",
    "TimescaleDB chunk metadata could not be inspected safely": (
        "No se pudieron leer los metadatos de fragmentos de TimescaleDB de forma segura"
    ),
    "TimescaleDB chunk metadata could not be read": "No se pudieron leer los metadatos de fragmentos de TimescaleDB",
    "TimescaleDB chunk planning timed out": (
        "Se agotó el tiempo para planificar la operación con fragmentos de TimescaleDB"
    ),
    "Compress 1 chunk of {target} as a job": "Tarea: comprimir un fragmento de {target}",
    "Compress {count} chunks of {target} as a job": 'Tarea: comprimir fragmentos de {target} ({count})',
    "Decompress 1 chunk of {target} as a job": "Tarea: descomprimir un fragmento de {target}",
    "Decompress {count} chunks of {target} as a job": 'Tarea: descomprimir fragmentos de {target} ({count})',
    "Already compressed and left as they are: {count}": "Ya comprimidos y dejados como están: {count}",
    "Already decompressed and left as they are: {count}": "Ya descomprimidos y dejados como están: {count}",
    "Compressed chunks stay readable; queries and writes touching a chunk may wait while it is rewritten": (
        "Los fragmentos comprimidos siguen siendo legibles; las consultas y escrituras que tocan un fragmento "
        "pueden esperar mientras se reescribe"
    ),
    "Decompressed chunks take more space; a compression policy may compress them again on its own schedule": (
        "Los fragmentos descomprimidos ocupan más espacio; una política de compresión puede volver a comprimirlos "
        "según su propia programación"
    ),
    "Each chunk is converted in its own transaction; cancelling keeps the chunks already converted": (
        "Cada fragmento se procesa en su propia transacción; si se cancela, se conservan los fragmentos ya "
        "procesados"
    ),
    "The hypertable could not be found; nothing was converted": "No se encontró la hipertabla; no se modificó nada",
    "Every whole chunk inside this window is already compressed": (
        "Todos los fragmentos completos de esta ventana ya están comprimidos"
    ),
    "No whole chunk inside this window is compressed": "Ningún fragmento completo de esta ventana está comprimido",
    "No whole chunk lies inside this window": "No hay ningún fragmento completo dentro de esta ventana",
    "More than {count} chunks lie inside this window; narrow it": (
        "Hay más de {count} fragmentos dentro de esta ventana; redúzcala"
    ),
    "This chunk is in use; nothing was converted": "Este fragmento está en uso; no se modificó nada",
    "The source cancelled converting this chunk after its fifteen minutes; it was rolled back": (
        "La fuente canceló el procesamiento de este fragmento después de sus quince minutos; se revirtió"
    ),
    "This connection may not convert this chunk": "Esta conexión no puede procesar este fragmento",
    "The connection was lost while this chunk was being converted; its outcome is unknown": (
        "Se perdió la conexión mientras se procesaba este fragmento; su resultado es desconocido"
    ),
    "The source could not be reached; nothing was converted": "No se pudo contactar con la fuente; no se modificó nada",
    "The hypertable could not be checked in time; nothing was converted": (
        "No se pudo comprobar la hipertabla a tiempo; no se modificó nada"
    ),
    "The hypertable could not be checked safely; nothing was converted": (
        "No se pudo comprobar la hipertabla de forma segura; no se modificó nada"
    ),
    "The hypertable or its TimescaleDB API changed after review; nothing was converted": (
        "La hipertabla o su API de TimescaleDB cambiaron después de la revisión; no se modificó nada"
    ),
    "This chunk is no longer part of the hypertable": "Este fragmento ya no forma parte de la hipertabla",
    "The source could not be reached or prepared; nothing was converted": (
        "No se pudo contactar con la fuente ni prepararla; no se modificó nada"
    ),
    "The source refused to convert this chunk": "La fuente se negó a procesar este fragmento",
    # Mantenimiento de fragmentos.
    "Drop chunks": "Eliminar fragmentos",
    "Drop these chunks and every row in them? This cannot be undone.": (
        "¿Eliminar estos fragmentos y todas sus filas? Esta acción no se puede deshacer."
    ),
    "Detach chunks": "Separar fragmentos",
    "Merge chunks": "Combinar fragmentos",
    "Merge chunks, reads going on": "Combinar fragmentos sin interrumpir las lecturas",
    "Move chunks to a tablespace": "Mover fragmentos a un espacio de tablas",
    "Reorder chunks by an index": "Reordenar fragmentos por un índice",
    "Split a chunk": "Dividir un fragmento",
    "Attach a table as a chunk": "Adjuntar una tabla como fragmento",
    "Drop chunks…": "Eliminar fragmentos…",
    "Move chunks to a tablespace…": "Mover fragmentos a un espacio de tablas…",
    "Reorder chunks by an index…": "Reordenar fragmentos por un índice…",
    "Detach chunks…": "Separar fragmentos…",
    "Merge chunks…": "Combinar fragmentos…",
    "Merge chunks, reads going on…": "Combinar fragmentos sin interrumpir las lecturas…",
    "Tablespace": "Espacio de tablas",
    "An existing tablespace this connection may create in": (
        "Un espacio de tablas existente en el que esta conexión puede crear objetos"
    ),
    "Order rows by index": "Ordenar filas por índice",
    "Leave empty for the index on the time column": "Déjelo vacío para usar el índice sobre la columna de tiempo",
    "Index tablespace": "Espacio de tablas de índices",
    "Leave empty to move the indexes with the chunk": (
        "Déjelo vacío para mover los índices junto con el fragmento"
    ),
    "Index": "Índice",
    "An index of this hypertable to order rows by": "Un índice de esta hipertabla por el que ordenar las filas",
    "Split at": "Dividir en",
    "With its time zone; the chunk holding this instant is split at it": (
        "Con su zona horaria; el fragmento que contiene este instante se divide en él"
    ),
    "Schema of the table": "Esquema de la tabla",
    "Table": "Tabla",
    "A table with the hypertable's columns, such as a detached chunk": (
        "Una tabla con las columnas de la hipertabla, como un fragmento separado"
    ),
    "Covering from": "Cubre desde",
    "Until": "Hasta",
    "Either a window or picked chunks, not both": (
        "Indique una ventana o fragmentos seleccionados, pero no ambos"
    ),
    "Give where the window ends": "Indique dónde termina la ventana",
    "With the chunk": "Con el fragmento",
    "The index on the time column": "El índice sobre la columna de tiempo",
    "A value of \"{column}\", the {type} column the hypertable is partitioned by": (
        "Un valor de «{column}», la columna de tipo {type} por la que está particionada la hipertabla"
    ),
    "A value of \"{column}\", the {type} column the hypertable is partitioned by; leave empty for every earlier chunk": (
        "Un valor de «{column}», la columna de tipo {type} por la que está particionada la hipertabla; déjelo vacío para todos los fragmentos anteriores"
    ),
    "A value of \"{column}\", the {type} column the hypertable is partitioned by; the chunk holding it is split at it": (
        "Un valor de «{column}», la columna de tipo {type} por la que está particionada la hipertabla; el fragmento que lo contiene se divide en ese punto"
    ),
    "Drop 1 chunk of {target} as a job": "Tarea: eliminar un fragmento de {target}",
    "Drop {count} chunks of {target} as a job": 'Tarea: eliminar fragmentos de {target} ({count})',
    "Move 1 chunk of {target} as a job": "Tarea: mover un fragmento de {target}",
    "Move {count} chunks of {target} as a job": 'Tarea: mover fragmentos de {target} ({count})',
    "Reorder 1 chunk of {target} as a job": "Tarea: reordenar un fragmento de {target}",
    "Reorder {count} chunks of {target} as a job": 'Tarea: reordenar fragmentos de {target} ({count})',
    "Detach 1 chunk of {target} as a job": "Tarea: separar un fragmento de {target}",
    "Detach {count} chunks of {target} as a job": 'Tarea: separar fragmentos de {target} ({count})',
    "Merge {count} chunks of {target} into one as a job": 'Tarea: combinar fragmentos de {target} ({count}) en uno',
    "Split {chunk} at {point} as a job": "Tarea: dividir {chunk} en {point}",
    "Attach {table} to {target} as a chunk as a job": "Tarea: adjuntar {table} a {target} como fragmento",
    "Exactly the chunks picked in the Chunks report, each read again by name": (
        "Exactamente los fragmentos seleccionados en el informe «Fragmentos»; cada uno se vuelve a leer por su "
        "nombre"
    ),
    "Left as they are, already in {tablespace}: {count}": "Dejados como están, ya en {tablespace}: {count}",
    "Left as they are, compressed, which reorder_chunk does not rewrite: {count}": (
        "Dejados como están, comprimidos, que reorder_chunk no reescribe: {count}"
    ),
    "Left as they are, compressed; TimescaleDB detaches only uncompressed chunks: {count}": (
        "Dejados como están, comprimidos; TimescaleDB solo separa fragmentos sin comprimir: {count}"
    ),
    "Left as they are: {count}": "Dejados como están: {count}",
    "Every row in these chunks is deleted; each chunk is dropped by name, never by an age read when the job runs": (
        "Se eliminan todas las filas de estos fragmentos; cada fragmento se elimina por su nombre, nunca por una "
        "antigüedad leída al ejecutarse la tarea"
    ),
    "Each chunk becomes an ordinary table under its own name and leaves the hypertable's queries; Detached chunks lists it, and Attach chunk brings it back": (
        "Cada fragmento se convierte en una tabla normal con su propio nombre y deja de aparecer en las consultas "
        "de la hipertabla; «Fragmentos separados» lo muestra y «Adjuntar tabla como fragmento» lo recupera"
    ),
    "The chunks become one, covering their whole range; the table is locked while they merge": (
        "Los fragmentos se convierten en uno solo que cubre todo su rango; la tabla se bloquea mientras se combinan"
    ),
    "The chunks become one, covering their whole range; reads go on meanwhile, writes to them wait": (
        "Los fragmentos se convierten en uno solo que cubre todo su rango; las lecturas continúan mientras tanto "
        "y las escrituras en ellos esperan"
    ),
    "Each chunk is copied to the tablespace and the old copy removed; reads and writes to it wait meanwhile": (
        "Cada fragmento se copia al espacio de tablas y se elimina la copia antigua; las lecturas y escrituras en "
        "él esperan mientras tanto"
    ),
    "Each chunk is rewritten in the index's order, which speeds reads along it; reads and writes wait meanwhile": (
        "Cada fragmento se reescribe en el orden del índice, lo que acelera las lecturas a través de él; las "
        "lecturas y escrituras esperan mientras tanto"
    ),
    "The chunk becomes two, divided at this point; the table is locked while it splits": (
        "El fragmento se divide en dos en este punto; la tabla se bloquea mientras se divide"
    ),
    "Its rows join the hypertable's queries; TimescaleDB refuses a table whose columns or rows do not fit": (
        "Sus filas se unen a las consultas de la hipertabla; TimescaleDB rechazará una tabla cuyas columnas o "
        "filas no encajen"
    ),
    "The hypertable could not be found; nothing was changed": "No se encontró la hipertabla; no se modificó nada",
    "This hypertable is partitioned by the integer column \"{column}\"; give its values, not instants": (
        "Esta hipertabla está particionada por la columna entera «{column}»; indique sus valores, no instantes"
    ),
    "This hypertable is partitioned by time on \"{column}\"; give instants, not numbers": (
        "Esta hipertabla está particionada por tiempo en «{column}»; indique instantes, no números"
    ),
    "Chunks of a hypertable partitioned by hash on {columns} are not merged here: which partition a chunk is in is not public, so the result could not be checked first": (
        "Los fragmentos de una hipertabla particionada por hash en {columns} no se combinan aquí: no se revela en qué partición está cada fragmento, así que el resultado no se puede comprobar de antemano"
    ),
    "Chunks of a hypertable partitioned by hash on {columns} are not attached here: which partition a chunk is in is not public, so the result could not be checked first": (
        "Los fragmentos de una hipertabla particionada por hash en {columns} no se adjuntan aquí: no se revela en qué partición está cada fragmento, así que el resultado no se puede comprobar de antemano"
    ),
    "TimescaleDB splits no chunk of a hypertable partitioned by hash as well as by time": (
        "TimescaleDB no divide fragmentos de una hipertabla particionada tanto por hash como por tiempo"
    ),
    "Pick at least one chunk": "Seleccione al menos un fragmento",
    "Pick at most {count} chunks at a time": "Seleccione como máximo {count} fragmentos a la vez",
    "\"{name}\" is not a chunk of this hypertable any more": "«{name}» ya no es un fragmento de esta hipertabla",
    "Tablespace \"{name}\" does not exist or this connection may not create in it": (
        "El espacio de tablas «{name}» no existe o esta conexión no puede crear objetos en él"
    ),
    "This hypertable has no index \"{index}\"": "Esta hipertabla no tiene el índice «{index}»",
    "Every whole chunk inside this window is already in {tablespace}": (
        "Todos los fragmentos completos de esta ventana ya están en {tablespace}"
    ),
    "Every picked chunk is already in {tablespace}": "Todos los fragmentos seleccionados ya están en {tablespace}",
    "Every whole chunk inside this window is compressed, which reorder_chunk does not rewrite": (
        "Todos los fragmentos completos de esta ventana están comprimidos, y reorder_chunk no reescribe los "
        "comprimidos"
    ),
    "Every picked chunk is compressed, which reorder_chunk does not rewrite": (
        "Todos los fragmentos seleccionados están comprimidos, y reorder_chunk no reescribe los comprimidos"
    ),
    "Every whole chunk inside this window is compressed; TimescaleDB detaches only uncompressed chunks": (
        "Todos los fragmentos completos de esta ventana están comprimidos; TimescaleDB solo separa fragmentos sin "
        "comprimir"
    ),
    "Every picked chunk is compressed; TimescaleDB detaches only uncompressed chunks": (
        "Todos los fragmentos seleccionados están comprimidos; TimescaleDB solo separa fragmentos sin comprimir"
    ),
    "Name an index: moving a chunk rewrites it in an index's order": (
        "Indique un índice: al mover un fragmento se reescribe en el orden de un índice"
    ),
    "A merge needs at least two chunks": "Para combinar se necesitan al menos dos fragmentos",
    "Chunks \"{before}\" and \"{after}\" are not adjacent; choose chunks that touch": (
        "Los fragmentos «{before}» y «{after}» no son adyacentes; elija fragmentos que se toquen"
    ),
    "TimescaleDB {version} cannot merge compressed chunks; decompress them first": (
        "TimescaleDB {version} no puede combinar fragmentos comprimidos; descomprímalos primero"
    ),
    "No chunk holds this point strictly inside its range": (
        "Ningún fragmento contiene este punto estrictamente dentro de su rango"
    ),
    "There is no table \"{schema}\".\"{table}\"": "No existe la tabla «{schema}».«{table}»",
    "Only an ordinary table can become a chunk": "Solo una tabla normal puede convertirse en fragmento",
    "Only the table's owner can attach it": "Solo el propietario de la tabla puede adjuntarla",
    "A hypertable cannot become a chunk": "Una hipertabla no puede convertirse en fragmento",
    "This table is already a chunk": "Esta tabla ya es un fragmento",
    "A table that uses inheritance cannot become a chunk": (
        "Una tabla que usa herencia no puede convertirse en fragmento"
    ),
    "Chunk \"{name}\" already covers part of this range": "El fragmento «{name}» ya cubre parte de este rango",
    "The range is empty once read in the column's type": "El rango queda vacío al leerse con el tipo de la columna",
    "This chunk is in use; nothing was changed": "Este fragmento está en uso; no se modificó nada",
    "The source cancelled this unit after its fifteen minutes; it was rolled back": (
        "La fuente canceló este paso después de sus quince minutos; se revirtió"
    ),
    "This connection may not change this chunk": "Esta conexión no puede cambiar este fragmento",
    "The connection was lost while this unit was running; its outcome is unknown": (
        "Se perdió la conexión mientras se ejecutaba este paso; su resultado es desconocido"
    ),
    "The hypertable could not be checked in time; nothing was changed": (
        "No se pudo comprobar la hipertabla a tiempo; no se modificó nada"
    ),
    "The hypertable or its chunks changed after review; nothing was changed": (
        "La hipertabla o sus fragmentos cambiaron después de la revisión; no se modificó nada"
    ),
    "The hypertable could not be checked safely; nothing was changed": (
        "No se pudo comprobar la hipertabla de forma segura; no se modificó nada"
    ),
    "The source could not be reached; nothing was changed": "No se pudo contactar con la fuente; no se modificó nada",
    "The table to attach is gone; nothing was changed": (
        "La tabla que se iba a adjuntar ya no existe; no se modificó nada"
    ),
    "This chunk was compressed after review; it was left as it is": (
        "Este fragmento se comprimió después de la revisión; se dejó como está"
    ),
    "These chunks changed after review; nothing was merged": (
        "Estos fragmentos cambiaron después de la revisión; no se combinó nada"
    ),
    "The index to order rows by is gone; nothing was changed": (
        "El índice por el que se iban a ordenar las filas ya no existe; no se modificó nada"
    ),
    "The source could not be reached or prepared; nothing was changed": (
        "No se pudo contactar con la fuente ni prepararla; no se modificó nada"
    ),
    "The source refused this unit; nothing was changed": "La fuente rechazó este paso; no se modificó nada",
    "This is not offered over these rows": "Esta acción no está disponible para estas filas",
    "A chunk is named by its schema and its name": "Un fragmento se identifica por su esquema y su nombre",
    "The picked chunks belong to {count} hypertables; pick chunks of one": (
        "Los fragmentos seleccionados pertenecen a {count} hipertablas; elija fragmentos de una sola"
    ),
    "Some picked rows are not chunks any more; read the report again": (
        "Algunas filas seleccionadas ya no son fragmentos; vuelva a leer el informe"
    ),
    # Omisión de fragmentos.
    "Skip chunks by a column": "Omitir fragmentos por una columna",
    "Stop skipping chunks by a column": "Dejar de omitir fragmentos por una columna",
    "Column": "Columna",
    "An integer, date or timestamp column queries filter on": (
        "Una columna entera o de tipo date o timestamp por la que filtran las consultas"
    ),
    "The hypertable could not be inspected safely": "No se pudo inspeccionar la hipertabla de forma segura",
    "TimescaleDB keeps ranges only of integer, date and timestamp columns, not of \"{column}\" ({type})": (
        "TimescaleDB solo guarda rangos de columnas enteras y de tipo date y timestamp, no de «{column}» ({type})"
    ),
    "Planning chunk skipping timed out": "Se agotó el tiempo para planificar la omisión de fragmentos",
    "Chunks record the range of {column} as they are compressed, and a query filtering on it skips the chunks outside": (
        "Al comprimirse, los fragmentos registran el rango de {column}, y una consulta que filtra por él omite los fragmentos fuera del rango"
    ),
    "Chunks stop recording the range of {column}, if they did": (
        "Los fragmentos dejan de registrar el rango de {column}, si lo hacían"
    ),
    "Changes nothing if it already holds: TimescaleDB keeps which columns record ranges where this application does not read": (
        "No cambia nada si ya es así: TimescaleDB guarda qué columnas registran rangos en un lugar que esta "
        "aplicación no lee"
    ),
    "timescaledb.enable_chunk_skipping is off for this connection; queries use the ranges only in sessions that turn it on": (
        "timescaledb.enable_chunk_skipping está desactivado para esta conexión; las consultas usan los rangos "
        "solo en las sesiones que lo activan"
    ),
    "Skip chunks by {column} on {target}": 'Omitir fragmentos de {target} por {column}',
    "Stop skipping chunks by {column} on {target}": 'Dejar de omitir fragmentos de {target} por {column}',
    "Review the chunk skipping plan before applying it": (
        "Revise el plan de omisión de fragmentos antes de aplicarlo"
    ),
    "Chunk skipping turned on": "Omisión de fragmentos activada",
    "Chunk skipping turned off": "Omisión de fragmentos desactivada",
    # Ajustes de hipertabla: leer la hipertabla.
    "Hypertable settings": "Ajustes de hipertabla",
    "Reading the hypertable timed out": "Se agotó el tiempo para leer la hipertabla",
    "Job {job} drops chunks {chunks}, every {every}": "La tarea {job} elimina los fragmentos {chunks}, cada {every}",
    "Job {job} drops chunks {chunks}, every {every}; paused": (
        "La tarea {job} elimina los fragmentos {chunks}, cada {every}; en pausa"
    ),
    "Job {job} compresses chunks {chunks}, every {every}": (
        "La tarea {job} comprime los fragmentos {chunks}, cada {every}"
    ),
    "Job {job} compresses chunks {chunks}, every {every}; paused": (
        "La tarea {job} comprime los fragmentos {chunks}, cada {every}; en pausa"
    ),
    "Job {job} reorders chunks by {index}": "La tarea {job} reordena los fragmentos por {index}",
    "Job {job} reorders chunks by {index}; paused": (
        "La tarea {job} reordena los fragmentos por {index}; en pausa"
    ),
    "Job {job} reorders chunks by an index this editor cannot read": (
        "La tarea {job} reordena los fragmentos por un índice que este editor no puede leer"
    ),
    "Job {job} reorders chunks by an index this editor cannot read; paused": (
        "La tarea {job} reordena los fragmentos por un índice que este editor no puede leer; en pausa"
    ),
    "The current sparse indexes could not be read": "No se pudieron leer los índices dispersos actuales",
    "This hypertable has a sparse index of a kind this editor does not know; manage it with SQL": (
        "Esta hipertabla tiene un índice disperso de un tipo que este editor no conoce; gestiónelo con SQL"
    ),
    "The current columnstore settings could not be read": (
        "No se pudieron leer los ajustes actuales del almacén columnar"
    ),
    "This hypertable merges compressed chunks by a time interval; manage it with SQL": (
        "Esta hipertabla combina fragmentos comprimidos por un intervalo de tiempo; gestiónelo con SQL"
    ),
    "This hypertable has several compaction policy jobs; manage them with SQL": (
        "Esta hipertabla tiene varias tareas de política de compactación; gestiónelas con SQL"
    ),
    "This hypertable has several reorder policy jobs; manage them with SQL": (
        "Esta hipertabla tiene varias tareas de política de reordenación; gestiónelas con SQL"
    ),
    "The existing reorder policy could not be read safely; manage it with SQL": (
        "No se pudo leer la política de reordenación actual de forma segura; gestiónela con SQL"
    ),
    "TimescaleDB {version} partitions by UUIDv7 only partly; it is edited here from 2.25": (
        "TimescaleDB {version} particiona por UUIDv7 solo en parte; aquí se edita a partir de 2.25"
    ),
    "Only timestamp, date, UUIDv7 and integer time dimensions are edited here": (
        "Aquí solo se editan dimensiones temporales de tipo timestamp, date, UUIDv7 y enteras"
    ),
    "The current chunk interval could not be read": "No se pudo leer el intervalo de fragmentos actual",
    "Only hash dimensions beside the time dimension are edited here": (
        "Aquí solo se editan dimensiones hash además de la temporal"
    ),
    "The hypertable's chunks and tablespaces could not be read": (
        "No se pudieron leer los fragmentos y los espacios de tablas de la hipertabla"
    ),
    "This connection may not create functions in schema \"{schema}\"": (
        "Esta conexión no puede crear funciones en el esquema «{schema}»"
    ),
    "A function named \"{name}\" already exists; choose it from the list or another name": (
        "Ya existe una función llamada «{name}»; elíjala de la lista o elija otro nombre"
    ),
    "A chunk interval of an integer column is a number of its values": (
        "El intervalo de fragmentos de una columna entera es un número de sus valores"
    ),
    "A chunk interval of a {type} column is at most {count}": (
        "El intervalo de fragmentos de una columna de tipo {type} es como máximo {count}"
    ),
    "A chunk interval is counted in minutes, hours, days or weeks": (
        "El intervalo de fragmentos se cuenta en minutos, horas, días o semanas"
    ),
    # Ajustes de hipertabla: planificar el cambio.
    "Locks this hypertable exclusively while it changes; its reads and writes wait until it commits": (
        "Bloquea esta hipertabla en exclusiva mientras cambia; sus lecturas y escrituras esperan a que se "
        "confirme"
    ),
    "Other changes to this hypertable's settings wait until it commits": (
        "Otros cambios en los ajustes de esta hipertabla esperan a que se confirme"
    ),
    "A chunk interval of this hypertable is counted in days or weeks": (
        "El intervalo de fragmentos de esta hipertabla se cuenta en días o semanas"
    ),
    "A chunk interval of this hypertable is counted in minutes or hours or days or weeks": (
        "El intervalo de fragmentos de esta hipertabla se cuenta en minutos, horas, días o semanas"
    ),
    "A chunk interval of this column is counted in days or weeks": (
        "El intervalo de fragmentos de esta columna se cuenta en días o semanas"
    ),
    "A chunk interval of this column is counted in minutes or hours or days or weeks": (
        "El intervalo de fragmentos de esta columna se cuenta en minutos, horas, días o semanas"
    ),
    "Column \"{column}\" has a type that cannot be used as a hash dimension": (
        "El tipo de la columna «{column}» no se puede usar como dimensión hash"
    ),
    "Column \"{column}\" has a type that cannot be used as a minmax sparse index": (
        "El tipo de la columna «{column}» no se puede usar como índice disperso misma"
    ),
    "Column \"{column}\" has a type that cannot be used as a segment column": (
        "El tipo de la columna «{column}» no se puede usar como columna de segmentación"
    ),
    "Column \"{column}\" has a type that cannot be used as an order column": (
        "El tipo de la columna «{column}» no se puede usar como columna de ordenación"
    ),
    "TimescaleDB cannot remove the hash dimension on \"{column}\"": (
        "TimescaleDB no puede eliminar la dimensión hash de «{column}»"
    ),
    "A hash dimension can only be added while the hypertable holds no chunks": (
        "Solo se puede añadir una dimensión haz mientras la hipertabla no tiene fragmentos"
    ),
    "The time column cannot also be a hash dimension": (
        "La columna de tiempo tampoco puede ser una dimensión hash"
    ),
    "Unique key \"{key}\" must include \"{column}\" before it can be a hash dimension": (
        'Para que «{column}» sea una dimensión hash, la clave única «{key}» debe incluirla'
    ),
    "TimescaleDB {version} has no sparse indexes; they arrived in 2.22": (
        "TimescaleDB {version} no tiene índices dispersos; llegaron en 2.22"
    ),
    "Column \"{column}\" has the same sparse index twice": (
        "La columna «{column}» tiene el mismo índice disperso dos veces"
    ),
    "Sparse indexes need the order to be named; choose the columns to order by": (
        "Los índices dispersos necesitan que se indique el orden; elija las columnas por las que ordenar"
    ),
    "Column \"{column}\" is listed more than once in the columnstore settings": (
        "La columna «{column}» aparece más de una vez en los ajustes del almacén columnar"
    ),
    "The columnstore cannot be turned off while chunks are compressed; decompress them first": (
        "El almacén columnar no se puede desactivar mientras haya fragmentos comprimidos; descomprímalos primero"
    ),
    "TimescaleDB {version} cannot return a setting to its own choice; name the columns instead": (
        "TimescaleDB {version} no puede devolver un ajuste a su propia elección; indique las columnas"
    ),
    "Merging compressed chunks is set in time, which an integer column does not count in": (
        "La combinación de fragmentos comprimidos se define en tiempo, y una columna entera no lo mide"
    ),
    "A merge interval is counted in the units of the chunk interval": (
        "El intervalo de combinación se cuenta en las unidades del intervalo de fragmentos"
    ),
    "The merge interval must be a whole multiple of the chunk interval, larger than it": (
        "El intervalo de combinación debe ser un múltiplo entero del intervalo de fragmentos y mayor que él"
    ),
    "There is no retention policy to keep": "No hay ninguna política de retención que conservar",
    "There is no compression policy to keep": "No hay ninguna política de compresión que conservar",
    "The retention policy of an integer column is a number of its values": (
        "La política de retención de una columna entera es un número de sus valores"
    ),
    "The compression policy of an integer column is a number of its values": (
        "La política de compresión de una columna entera es un número de sus valores"
    ),
    "The retention policy of a {type} column is at most {count}": (
        "La política de retención de una columna de tipo {type} es como máximo {count}"
    ),
    "The compression policy of a {type} column is at most {count}": (
        "La política de compresión de una columna de tipo {type} es como máximo {count}"
    ),
    "The retention policy of a {type} column cannot count in plain numbers": (
        "La política de retención de una columna de tipo {type} no se puede expresar con números simples"
    ),
    "The compression policy of a {type} column cannot count in plain numbers": (
        "La política de compresión de una columna de tipo {type} no se puede expresar con números simples"
    ),
    "The retention policy of a {type} column cannot count in seconds": (
        "La política de retención de una columna de tipo {type} no se puede expresar en segundos"
    ),
    "The compression policy of a {type} column cannot count in seconds": (
        "La política de compresión de una columna de tipo {type} no se puede expresar en segundos"
    ),
    "The retention policy of a {type} column cannot count in minutes": (
        "La política de retención de una columna de tipo {type} no se puede expresar en minutos"
    ),
    "The compression policy of a {type} column cannot count in minutes": (
        "La política de compresión de una columna de tipo {type} no se puede expresar en minutos"
    ),
    "The retention policy of a {type} column cannot count in hours": (
        "La política de retención de una columna de tipo {type} no se puede expresar en horas"
    ),
    "The compression policy of a {type} column cannot count in hours": (
        "La política de compresión de una columna de tipo {type} no se puede expresar en horas"
    ),
    "The existing reorder policy is paused; remove it before setting a new one": (
        "La política de reordenación actual está en pausa; elimínela antes de establecer una nueva"
    ),
    "Only a hypertable partitioned by an integer column takes an integer_now function": (
        "Solo una hipertabla particionada por una columna entera acepta una función integer_now"
    ),
    "TimescaleDB cannot take an integer_now function away; keep it or choose another": (
        "TimescaleDB no puede quitar una función integer_now; consérvela o elija otra"
    ),
    "There is no integer_now function to keep": "No hay ninguna función integer_now que conservar",
    "{function} is not a function TimescaleDB accepts as integer_now of a {type} column": (
        "TimescaleDB no acepta {function} como integer_now de una columna de tipo {type}"
    ),
    "A {type} column cannot hold the seconds since 1970": (
        "Una columna de tipo {type} no puede contener los segundos desde 1970"
    ),
    "A {type} column cannot hold the milliseconds since 1970": (
        "Una columna de tipo {type} no puede contener los milisegundos desde 1970"
    ),
    "A {type} column cannot hold the microseconds since 1970": (
        "Una columna de tipo {type} no puede contener los microsegundos desde 1970"
    ),
    "TimescaleDB {version} has no compaction policy; it arrived in 2.29": (
        "TimescaleDB {version} no tiene política de compactación; llegó en 2.29"
    ),
    "A compaction policy merges compressed chunks; turn the columnstore on": (
        "Una política de compactación combina fragmentos comprimidos; active el almacén columnar"
    ),
    "Remove the columnstore policy to turn the columnstore off": (
        "Para desactivar el almacén columnar, elimine la política del almacén columnar"
    ),
    "Remove the compaction policy to turn the columnstore off": (
        "Para desactivar el almacén columnar, elimine la política de compactación"
    ),
    "An age policy on an integer column needs an integer_now function to tell the current value": (
        "Una política por antigüedad en una columna entera necesita una función integer_now que indique el valor actual"
    ),
    "Choose the time column the table is partitioned by": (
        "Elija la columna de tiempo por la que se particiona la tabla"
    ),
    "Choose the chunk interval": "Elija el intervalo de fragmentos",
    "TimescaleDB cannot change the time column of a hypertable": (
        "TimescaleDB no puede cambiar la columna de tiempo de una hipertabla"
    ),
    "Planning the hypertable change timed out": "Se agotó el tiempo para planificar el cambio de la hipertabla",
    # Ajustes de hipertabla: la vista previa.
    "TimescaleDB's choice for each chunk": "a elección de TimescaleDB para cada fragmento",
    "TimescaleDB's choice": "a elección de TimescaleDB",
    "none": "ninguno",
    "segment by {columns}": "segmentación: {columns}",
    "order by {columns}": "orden: {columns}",
    "sparse indexes {indexes}": "índices dispersos: {indexes}",
    "{kind} on {column}": "{kind} en {column}",
    "no merging of chunks": "sin combinación de fragmentos",
    "merge chunks into {length} as they are compressed": "combinar fragmentos hasta {length} al comprimirse",
    "Turn the columnstore on: {changes}": "Activar el almacén columnar: {changes}",
    "Columnstore settings for chunks compressed from now on: {changes}": (
        "Ajustes del almacén columnar para los fragmentos comprimidos a partir de ahora: {changes}"
    ),
    "Convert the table into a hypertable by {column} ({type}), chunks of {length}, and move its rows into chunks": (
        "Convertir la tabla en una hipertabla por {column} ({type}), con fragmentos de {length}, y mover sus filas a fragmentos"
    ),
    "Convert the table into a hypertable by {column} ({type}), chunks of {length}, while it is empty": (
        "Convertir la tabla en una hipertabla por {column} ({type}), con fragmentos de {length}, mientras está vacía"
    ),
    "Remove the retention policy (job {job})": "Eliminar la política de retención (tarea {job})",
    "Remove the columnstore policy (job {job})": "Eliminar la política del almacén columnar (tarea {job})",
    "Remove the reorder policy (job {job})": "Eliminar la política de reordenación (tarea {job})",
    "Remove the compaction policy (job {job})": "Eliminar la política de compactación (tarea {job})",
    "Add a retention policy: drop chunks older than {length}": (
        "Añadir una política de retención: eliminar fragmentos anteriores a {length}"
    ),
    "Add a columnstore policy: compress chunks older than {length}": (
        "Añadir una política del almacén columnar: comprimir fragmentos anteriores a {length}"
    ),
    "Add a compaction policy: merge small compressed chunks on TimescaleDB's schedule": (
        "Añadir una política de compactación: combinar fragmentos comprimidos pequeños según la programación de "
        "TimescaleDB"
    ),
    "Add a reorder policy by index {index}": "Añadir una política de reordenación por el índice {index}",
    "New chunks cover {length}; existing chunks keep their range": (
        "Los fragmentos nuevos cubren {length}; los fragmentos existentes conservan su rango"
    ),
    "Hash {column} into {partitions} partitions for new chunks": (
        "Aplicar hash a {column} en {partitions} particiones para los fragmentos nuevos"
    ),
    "Add a hash dimension on {column} with {partitions} partitions": (
        "Añadir una dimensión hash en {column} con {partitions} particiones"
    ),
    "Turn the columnstore off": "Desactivar el almacén columnar",
    "Place new chunks in tablespace {tablespace} too": (
        "Colocar también los fragmentos nuevos en el espacio de tablas {tablespace}"
    ),
    "Stop placing new chunks in tablespace {tablespace}": (
        "Dejar de colocar los fragmentos nuevos en el espacio de tablas {tablespace}"
    ),
    "Create function {function} returning the seconds since 1970 as {type}": (
        "Crear la función {function} que devuelve los segundos desde 1970 como {type}"
    ),
    "Create function {function} returning the milliseconds since 1970 as {type}": (
        "Crear la función {function} que devuelve los milisegundos desde 1970 como {type}"
    ),
    "Create function {function} returning the microseconds since 1970 as {type}": (
        "Crear la función {function} que devuelve los microsegundos desde 1970 como {type}"
    ),
    "Policies take the current value of the time column from {function}": (
        "Las políticas toman el valor actual de la columna de tiempo de {function}"
    ),
    "Moves about {count} rows into chunks as a job in Activity; the table is locked against reads and writes until it ends": (
        "Mueve unas {count} filas a fragmentos como tarea en Actividad; la tabla queda bloqueada para lecturas y escrituras hasta que termine"
    ),
    "Moves an unknown number of rows into chunks as a job in Activity; the table is locked against reads and writes until it ends": (
        "Mueve un número desconocido de filas a fragmentos como tarea en Actividad; la tabla queda bloqueada para "
        "lecturas y escrituras hasta que termine"
    ),
    "Rolled back whole if it fails, is cancelled or runs past {seconds} seconds; nothing is left half converted": (
        "Se revierte por completo si falla, se cancela o supera {seconds} segundos; no queda nada a medio convertir"
    ),
    "DataPlayer cannot turn a hypertable back into an ordinary table": (
        "DataPlayer no puede volver a convertir una hipertabla en una tabla normal"
    ),
    "TimescaleDB keeps dropping whole chunks past the retention age on its own schedule, after this session ends": (
        "TimescaleDB seguirá eliminando fragmentos completos que superen la antigüedad de retención según su "
        "propia programación, después de que termine esta sesión"
    ),
    "{target} already matches these settings": "{target} ya coincide con estos ajustes",
    "Change {target}": "Cambiar {target}",
    "Review the hypertable plan before applying it": "Revise el plan de la hipertabla antes de aplicarlo",
    "Moving rows into chunks runs as a job; start it from the plan": (
        "Mover filas a fragmentos se ejecuta como tarea; iníciela desde el plan"
    ),
    "Converted to a hypertable": "Convertida en hipertabla",
    "Hypertable changed: 1 change applied": "Hipertabla cambiada: se aplicó 1 cambio",
    "Hypertable changed: {count} changes applied": "Hipertabla cambiada: se aplicaron {count} cambios",
    "This change is applied at once rather than as a job": "Este cambio se aplica de inmediato, no como tarea",
    "The table could not be found; nothing was converted": "No se encontró la tabla; no se convirtió nada",
    "The table was renamed after review; nothing was converted": (
        "La tabla se renombró después de la revisión; no se convirtió nada"
    ),
    # Una tabla diseñada como hipertabla.
    "Hypertable": "Hipertabla",
    "Columnstore": "Almacén columnar",
    "Retention policy": "Política de retención",
    "Columnstore policy": "Política del almacén columnar",
    "Compaction policy": "Política de compactación",
    "Reorder policy": "Política de reordenación",
    "Integer now": "Integer now",
    "Function {name}": "Función {name}",
    "Hash dimension {column}": "Dimensión hash {column}",
    "The segment list names a column that is not there": "La lista de segmentación nombra una columna que no existe",
    "The order list names a column that is not there": "La lista de orden nombra una columna que no existe",
    "The sparse index names a column that is not there": "El índice disperso nombra una columna que no existe",
    "The time dimension names a column that is not there": "La dimensión temporal nombra una columna que no existe",
    "The hash dimension names a column that is not there": "La dimensión hash nombra una columna que no existe",
    "Choose the columns to segment by": "Elija las columnas por las que segmentar",
    "Choose the columns to order by": "Elija las columnas por las que ordenar",
    "Choose the columns of the sparse indexes": "Elija las columnas de los índices dispersos",
    "The reorder policy names an index that is not there": (
        "La política de reordenación nombra un índice que no existe"
    ),
    "The TimescaleDB API is split across schemas": "La API de TimescaleDB está repartida entre varios esquemas",
    "This setting cannot be made while the table is created": (
        "Este ajuste no se puede establecer al crear la tabla"
    ),
    "\"{column}\" cannot partition a hypertable; choose a timestamp or date column": (
        "«{column}» no puede particionar una hipertabla; elija una columna de tipo timestamp o date"
    ),
    "\"{column}\" partitions the hypertable, so it must have a value": (
        "«{column}» particiona la hipertabla, así que debe tener un valor"
    ),
    "TimescaleDB {version} partitions by UUIDv7 only partly; choose a timestamp column": (
        "TimescaleDB {version} particiona por UUIDv7 solo en parte; elija una columna de tipo timestamp"
    ),
}
