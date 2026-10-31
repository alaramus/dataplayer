# PostgreSQL

Una base de datos relacional. Exploras sus esquemas, lees tablas página a página,
editas filas y estructura, ejecutas SQL en una consola y copias datos de entrada
y salida. El funcionamiento general de las conexiones está en la página
[Conexiones](connections.md).

## Qué puedes ver

- Esquemas, tablas y vistas, y sus filas ordenadas y filtradas en el servidor
- Las columnas de una tabla, sus claves y las tablas a las que hace referencia
- Todas las filas coincidentes, descargadas como archivo
- Lo que está haciendo el servidor: procesos, ajustes, roles, extensiones
- Métricas del servidor en cuadros de mando

## Qué puedes cambiar

- Los datos y las columnas de una tabla
- Tablas y esquemas: crear, renombrar, mover, eliminar
- Un archivo CSV cargado en una tabla
- Roles
- Una copia de seguridad de toda la base de datos
- Hipertablas, compresión y retención de TimescaleDB, cuando está instalado

## Conectar

La página **Conexión** de la ventana pide:

- **Host** y **Puerto**, 5432 a menos que el servidor indique otra cosa;
- **Autenticación**: un usuario y una contraseña, o ninguna contraseña para un
  servidor que confía en la dirección desde la que te conectas;
- **Base de datos**, **Usuario** y **Contraseña**.

Una cadena de conexión como `postgresql://ann@db.example.com:5432/sales` pegada
en **URL** rellena estos campos. Una contraseña en la cadena pegada va al campo
de contraseña y sale de la cadena.

## El catálogo

Pulsar la conexión abre su catálogo.

- El control de esquemas de la parte superior elige qué esquemas se enumeran. Se
  pueden enumerar varios juntos; la lista indica entonces a qué esquema pertenece
  cada fila. La elección se recuerda en este navegador.
- Las filas son tablas, tablas participadas, vistas y vistas materializadas.
  Pulsar una abre sus filas en una pestaña.
- El cuadro de filtro reduce el nivel por nombre.
- **Sistema** es una sección de informes que el servidor da sobre sí mismo
  (consulta **Informes** más abajo).
- Marcar relaciones y elegir **Vínculos** en el menú de acciones las dibuja junto
  con las claves entre ellas como un diagrama.
- **Detalles** indica cómo se almacena una relación, quién es su propietario,
  cuántas columnas, índices y restricciones tiene, cuánto ocupa en disco y cuándo
  la midió el servidor por última vez.

Las tablas de los esquemas `pg_` y de `information_schema` pertenecen al
servidor. Se leen como cualquier otra tabla y nunca se cambian desde aquí.

## Leer filas

Una tabla se abre como una cuadrícula, de una página en una. La fila de comandos
situada encima tiene cinco grupos: **La vista**, **Leerlo como**, **Sacarlo**,
**Cambiar las filas** y **Esta pestaña**. Un comando que no se puede usar aquí se
queda en su sitio, atenuado, y explica por qué cuando pasas el puntero sobre él.

- **Ordenar**: la flecha en el encabezado de una columna. Se pueden ordenar
  varias columnas juntas, en orden.
- **Filtrar**: condiciones sobre columnas, unidas por AÑO. Lo que ofrece una
  columna depende de su tipo: comparaciones para números, fechas y texto;
  contiene y empieza por para texto; igualdad y «uno de una lista» para
  booleanos, UUID y enumeraciones; vacío o no vacío para todas las columnas.
- **Columnas**: fijar una columna a la izquierda, ocultarla, cambiar el orden,
  arrastrar su borde para cambiar el tamaño, hacer doble clic en el borde para
  ajustarlo.
- **Por página**, junto al patinador del pie: hasta 500 filas.
- **Actualizar automáticamente** vuelve a leer la página cada 1 s a 5 min. Espera
  mientras se edita una celda o se marcan filas.
- Una celda cuya columna forma parte de una clave externa tiene una flecha.
  Pulsarla muestra adónde lleva, y elegir ese destino abre la fila a la que
  apunta.
- **Qué apunta a esta fila** enumera las tablas cuyas claves apuntan aquí y abre
  en ellas las filas coincidentes.
- **Leer esta fila hacia abajo**, en la esquina de una fila, muestra una fila
  como una columna de nombres y valores. Sus flechas avanzan a las filas
  siguiente y anterior.
- Un valor JSON o de tipo arras se abre entero en un visor al hacer doble clic;
  Mayús + doble clic lo edita. **Copiar el valor completo** lo copia.
- Marcar celdas y pulsar Ctrl+C las copia como texto separado por tabulaciones.

Los filtros, el orden y las columnas de una tabla se recuerdan en este navegador.

## La estructura de una tabla

**Estructura** abre las columnas, claves, índices y restricciones de la tabla
junto a sus filas.

Con acceso **Cambiar estructura** puedes:

- añadir una columna, renombrarla, eliminarla, cambiar su tipo;
- establecer o quitar su valor predeterminado, y permitir o prohibir valores
  vacíos. Prohibirlos primero cuenta las filas vacías y se detiene si hay alguna;
- añadir o eliminar un índice;
- añadir o eliminar una clave única o una clave externa.

**Ver DDL**, sobre las filas, muestra el SQL que volvería a crear la tabla.
**Modelar como código**, en el menú de acciones del catálogo, escribe un esquema
o una tabla como modelo de SQLAlchemy, modelo de Django o documento DBML y lo
descarga.

## Editar filas

Con acceso **Editar filas**:

- haz doble clic en una celda para cambiarla. **Establecer SQL NULA** guarda un
  valor vacío, que no es lo mismo que texto vacío;
- **Insertar fila** añade una fila al final de la página. Las columnas con valor
  predeterminado se pueden dejar como están;
- marca filas enteras y pulsa **Eliminar las filas seleccionadas**. Se eliminan
  todas, o ninguna;
- pega un bloque de celdas copiadas en una selección con **Pegar en la
  selección**. Antes se comprueba cada valor con el tipo de su columna, y no se
  escribe nada si alguno falla.

Si alguien cambió una fila después de que la leyeras, se rechaza tu cambio en
lugar de escribir encima del suyo. Recarga e inténtalo de nuevo.

Las filas solo se pueden eliminar de una tabla con clave primaria. Las vistas son
de solo lectura.

## Tablas y esquemas

El menú de acciones del catálogo, sobre un esquema o sobre relaciones marcadas,
ofrece:

- **Nuevo esquema**, **Renombrar esquema**, **Eliminar esquema**;
- **Crear tabla**: diseña las columnas, claves e índices, revisa el SQL que se
  ejecutará y luego créala;
- **Renombrar**, **Mover a esquema**, **Eliminar**. Eliminar varias relaciones a
  la vez es un solo paso: se van todas, o no se va ninguna.

Lo que se llevaría por delante una eliminación se muestra antes de que confirmes.

## Traer datos y sacarlos

- **Cargar desde CSV**, sobre un esquema: sube un archivo CSV y crea una tabla
  con él.
- **Traer filas**, sobre una tabla: elige una tabla en cualquier conexión,
  empareja sus columnas con las de esta tabla, previsualiza y copia las filas.
- **Guardar estas filas como una nueva tabla o archivo** copia las filas en
  pantalla a una nueva tabla en otra conexión, o a un archivo CSV en una carpeta.
- **Descargar** pregunta por **Página actual** o **Todas las filas
  coincidentes**, y si se debe descargar el archivo o **Guardar en mis
  archivos**.
- **Copiar** tablas en el catálogo y **Pegar** en un esquema de otra conexión
  PostgreSQL: se copian con sus columnas, claves e índices. Se pregunta si las
  claves externas entre ellas vienen también.
- Pegar tablas copiadas en una carpeta de una conexión de archivos o SSH guarda
  cada una como un archivo CSV.

Las copias largas se ejecutan en segundo plano. La campana de actividad muestra
cómo van y puede detenerlas.

## La consola SQL

**Consultas**, en la barra de herramientas izquierda, enumera tus consultas
guardadas e inicia una **Nueva consulta** en una conexión. **Abrir como
consulta** sobre una tabla inicia una en esa tabla.

- **Ejecutar** ejecuta la selección, o la instrucción bajo el cursor. **Ejecutar
  script** ejecuta todo el texto.
- Los resultados se muestran bajo el editor y se pueden paginar, filtrar,
  ordenar, descargar y representar en gráficos.
- **Explicar** muestra el plan de una instrucción sin ejecutarla.
- Los cambios se confirman de inmediato, a menos que **Manual** esté activado.
  Entonces la consola mantiene una transacción abierta hasta **Confirmar** o
  **Revertir**.
- El ajuste **Consolas** de la conexión decide si se permiten los cambios, si se
  pregunta cada vez o si se rechazan.
- Cambiar la estructura (tablas, vistas, índices, esquemas) siempre se pregunta.
  Un cambio destructivo se prueba primero dentro de una transacción, y se te
  muestra lo que haría.
- El editor completa nombres de esquemas, tablas y columnas.
- Cada ejecución se conserva en el historial de la consulta.

## psql

**Abrir un terminal** en una conexión PostgreSQL tuya inicia `psql`, con la
sesión de la conexión y en su base de datos, en un contenedor que inicia este
servidor; no a través de un túnel SSH. Cerrar el terminal o `\q` lo termina.

## Informes

**Sistema** en el catálogo contiene seis informes sobre el servidor. Se leen como
tablas, y se pueden ordenar, filtrar, descargar y representar en gráficos.

- **Procesos**: qué está conectado y qué hace cada conexión. Cada fila tiene
  **Cancelar consulta** y **Terminar**. El informe se vuelve a leer cada cinco
  segundos.
- **Ajustes**: la configuración del servidor.
- **Espacios de tablas**, **Rutinas**.
- **Roles**: los usuarios del servidor. **Nuevo rol** sobre las filas crea uno.
  Solo lo tiene el propietario de la conexión.
- **Extensiones**: qué se puede instalar y qué está instalado. Cada fila tiene
  **Instalar** o **Quitar**.

## Copias de seguridad

**Copias de seguridad**, en el menú de acciones del catálogo, enumera las copias
de seguridad de esta base de datos guardadas en tu almacenamiento personal.

- **Copiar esta base de datos** crea una nueva. Se ejecuta en segundo plano.
- **Restaurar** devuelve una a esta base de datos. Reemplaza los objetos que
  contiene la copia, y pregunta primero.
- **Eliminar esta copia de seguridad** quita una.

Solo el propietario de la conexión puede hacer copias de seguridad. El botón está
atenuado cuando esta instalación no puede ejecutar el programa de copias de
seguridad.

## TimescaleDB

Cuando la base de datos tiene la extensión TimescaleDB, las hipertablas y los
agregados continuos se marcan en el catálogo, y el menú de acciones de una
hipertabla ofrece:

- **Cambiar el intervalo de fragmentos**, **Configurar la compresión**;
- **Establecer la política de retención**, **Establecer la política de
  compresión**, **Establecer la política de actualización**, y quitar cada una de
  ellas;
- **Comprimir fragmentos**, **Descomprimir fragmentos**;
- **Convertir en hipertabla**, en una tabla normal.

El trabajo que toca muchos fragmentos se planifica primero y se muestra para
revisión antes de ejecutarse. Después se ejecuta en segundo plano, y la campana
de actividad muestra cuánto ha avanzado y qué pasó con cada fragmento.

## Métricas

Una conexión PostgreSQL puede informar de sus propios contadores a los cuadros de
mando: sesiones por estado, transacciones, filas leídas y escritas, bloques
leídos del disco y de la memoria, conflictos, interbloqueos y el tamaño de la
base de datos. El propietario lo activa en la ventana **Fuentes** del espacio
**Cuadros de mando**, y elige la frecuencia. El diseño preparado para ello se
llama **Base de datos PostgreSQL**.

## Límites

- Una página de filas contiene como máximo 500 filas.
- Un bloque pegado tiene como máximo 500 filas y 2000 celdas.
- Eliminar actúa sobre las filas de la página en la que estás.
- Los filtros se unen con AÑO. No hay OR.
