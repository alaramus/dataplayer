# Archivos

Tu almacenamiento personal en este servidor: una carpeta propia a la que nadie
más llega a menos que compartas una conexión con ella. Exploras carpetas, abres
archivos en el visor que les corresponde, los editas y mueves archivos de entrada
y salida. El funcionamiento general de las conexiones está en la página
[Conexiones](connections.md).

## Qué puedes ver

- Carpetas y archivos, y qué es cada uno: su tamaño, sus fechas, su formato
- Tablas en archivos CSV, TSV, Excel y Parquet, y en archivos de registro
- Documentos, código, imágenes, PDF, grabaciones y el contenido de archivos ZIP
- Archivos encontrados por nombre, o por el texto que contienen
- SQL ejecutado sobre tablas guardadas en archivos

## Qué puedes cambiar

- Archivos en un editor de texto
- Las filas y columnas de archivos CSV y TSV
- Archivos y carpetas: crear, subir, renombrar, eliminar, descargar
- Archivos comprimidos: empaquetar archivos en uno, o descomprimir uno
- Archivos copiados o movidos entre carpetas y conexiones

## Conectar

El único campo es **Ruta**: la carpeta dentro de tu almacenamiento personal en
la que se abre la conexión. `/` es la raíz de tu almacenamiento, `/reports/2026`
una carpeta dentro de él. No se puede llegar a nada fuera de tu almacenamiento.

**Conectar carpeta**, en el menú de acciones del catálogo sobre una carpeta, crea
una nueva conexión que se abre en esa carpeta.

## El catálogo

- La ruta del nivel en el que estás se muestra en la parte superior. **Copiar la
  ruta de este nivel** la copia, en la forma que acepta el campo **Ruta**.
- **El inicio de esta conexión** vuelve a donde se abre la conexión.
- El cuadro de filtro reduce el nivel por nombre.
- El botón de búsqueda de al lado busca las mismas palabras en todas las carpetas
  de debajo, por nombre. Mantén **Mayús** mientras lo pulsas para buscar dentro
  de los archivos; la primera vez, indica cuánto cuesta y pregunta. Una
  coincidencia muestra la línea donde se encontró. **Volver a la carpeta** sale
  de los resultados.
- Pulsar un archivo lo abre en una pestaña. Pulsar una carpeta, un libro de
  trabajo o un archivo comprimido ZIP entra en él.
- **Detalles**, en el menú de acciones, indica qué es un archivo o una carpeta:
  su tamaño, sus fechas, sus permisos, en qué se puede abrir y qué dice su
  formato de sí mismo (las columnas de un archivo Parquet, las hojas de un libro
  de trabajo, la duración de una grabación, el tamaño de una imagen).

## Abrir archivos

Un archivo se abre en el visor que le corresponde. Donde hay más de una forma de
abrirlo, las demás se ofrecen encima.

- **CSV y TSV** se abren como tablas. Cada columna es texto.
- **Libros de Excel** (`.xlsx`, `.xlsm`) se abren en su primera hoja visible. Las
  demás hojas están a lo largo del pie de la cuadrícula, donde las coloca una
  hoja de cálculo. Las fórmulas muestran el valor guardado por última vez en el
  archivo.
- **Parquet** se abre como una tabla con los tipos de columna que declara el
  archivo.
- **JSON** y **JSON lines** se abren como texto, y **Ver como tabla** los
  convierte en filas.
- **Registros** (`.log`) se abren como texto, y **Ver como tabla** divide cada
  línea en su hora, su nivel y su mensaje.
- **Markdown** se abre como documento, con una tabla de contenidos, código,
  matemáticas, gráficos y diagramas. **Exportar** lo guarda como una página HTML
  o lo imprime.
- **Texto y código** se abren en el editor con resaltado.
- **Imágenes**, **PDF**, **audio** y **vídeo** se abren en sus propios visores.
  Un PDF se puede buscar.
- Se entra en un **archivo comprimido ZIP** como en una carpeta, y los archivos
  de dentro se abren como cualquier otro, en solo lectura.

Las tablas de archivos se leen como cualquier tabla en la cuadrícula (consulta
[PostgreSQL](source-postgres.md) para la cuadrícula en sí), con dos diferencias:
un archivo no se puede ordenar, y un filtro solo coincide con un valor exacto.

## Editar

- Un archivo de texto, JSON, JSON lines o Markdown se abre en el editor.
  **Guardar** lo vuelve a escribir. Un archivo JSON debe seguir siendo válido
  para guardarse.
- Si el archivo cambió desde que lo abriste, se rechaza el guardado y no se
  escribe nada. **Recargar archivo** lo vuelve a leer.
- Se pueden editar archivos de hasta 4 MB. Un archivo mayor se abre en solo
  lectura e indica por qué.
- En una tabla CSV o TSV puedes cambiar celdas, insertar filas, eliminar las
  filas marcadas y añadir, renombrar o quitar columnas desde **Estructura**.

## Archivos y carpetas

El menú de acciones del catálogo ofrece, sobre el nivel en el que estás o sobre
lo que está marcado:

- **Nueva carpeta**, **Nuevo archivo**, **Subir archivos**. Una subida indica qué
  hacer cuando un nombre ya existe: detenerse, reemplazar el archivo o conservar
  ambos con un nombre nuevo;
- **Renombrar**, **Eliminar**. No hay papelera: un archivo eliminado desaparece;
- **Descargar**: un archivo tal cual; una carpeta, o varios archivos marcados,
  como un solo ZIP;
- **Archivar**: empaquetar lo marcado en un ZIP, tar, tar.GHz, tar.vez o tar.Hz;
- **Extraer**: descomprimir un archivo comprimido aquí, o en una carpeta propia;
- **Copiar** y **Cortar**, y luego **Pegar** donde los quieras. Funciona entre
  carpetas de una conexión y entre conexiones, incluidos los servidores SSH.
  Pegar una tabla de una base de datos en una carpeta la guarda como archivo CSV.

Una copia entre conexiones se ejecuta en segundo plano. La campana de actividad
muestra cómo va y puede detenerla.

## SQL sobre archivos

**Abrir como consulta** sobre una tabla, o **Nueva consulta** en **Consultas**
en la barra de herramientas izquierda, inicia una consola SQL en esta conexión.
Una tabla se nombra por su ruta entre comillas dobles, por ejemplo
`SELECT * FROM "sales/2026.csv"`. Se pueden consultar y combinar archivos CSV,
TSV, Parquet, JSON, JSON lines y de registro; las hojas de Excel todavía no. Nada
de lo que hace una consulta se escribe de vuelta en los archivos.

## Límites

- El editor admite archivos de hasta 4 MB.
- Una búsqueda dentro de archivos omite los archivos de más de 8 MB y se detiene
  tras leer 256 MB.
- Una carpeta enumera como máximo 2000 entradas.
- Un archivo dentro de un archivo comprimido se lee hasta 32 MB.
- Una descarga o un archivo comprimido contiene como máximo 10 000 archivos y
  2 GB.
