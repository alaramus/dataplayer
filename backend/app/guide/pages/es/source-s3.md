# S3

Amazon S3, o cualquier almacenamiento que hable su API. Exploras buckets y
carpetas y trabajas con los objetos como con tus propios archivos: tablas, SQL
sobre archivos, los visores y la búsqueda. Se inicia sesión con una clave de
acceso. Cómo funcionan las conexiones en general está en la página
[Conexiones](connections.md).

## Qué puedes ver

- Los buckets, y las carpetas y objetos que contienen
- Tablas en archivos CSV, TSV, Excel y Parquet, y en registros
- Documentos, código, imágenes, PDF, grabaciones y el contenido de archivos zip
- Objetos encontrados por nombre, o por el texto que contienen
- SQL ejecutado sobre tablas guardadas en objetos

## Conectar

La página **Conexión** de la ventana pide:

- **Punto de acceso**: la dirección del almacenamiento, como
  `https://s3.example.com`. Vacío es Amazon S3;
- **Región**: vacío es `us-east-1`;
- **Clave de acceso** y **Clave secreta**;
- **Bucket**: vacío muestra todos los buckets que la clave puede listar;
- **Carpeta**: dónde empieza la navegación dentro del bucket;
- **Direccionamiento**: «auto» es virtual-hosted en Amazon S3 y path-style en
  los demás, que todo almacenamiento compatible acepta;
- **Verificar el certificado**: desactívalo solo para un almacenamiento cuyo
  certificado hiciste tú.

## El catálogo y los objetos

Una conexión S3 se explora como una conexión [Archivos](source-file.md): el
mismo catálogo, la misma búsqueda por nombre y dentro de los archivos, los mismos
visores y el mismo SQL sobre archivos. **Descargar** trae un objeto, o una
carpeta como archivo comprimido.

En qué se diferencia un almacenamiento de un disco:

- Una carpeta es el comienzo común de unas claves, `reports/2026/`. Una carpeta
  vacía es un objeto vacío cuya clave termina en `/`, como las que crean las
  consolas de los proveedores.
- Una clave que no podría ser un nombre de archivo —con una parte vacía, `.` o
  `..`, una barra invertida o una unidad como `C:`— no se muestra. Sigue en el
  bucket.
- Un objeto de más de 200 MB no se abre como tabla, libro, archivo comprimido ni
  en SQL: descárgalo. El texto, las imágenes, los PDF y las grabaciones se abren
  sea cual sea su tamaño.
- Una búsqueda dentro de los objetos omite los de más de 1 MB y se detiene tras
  32 MB en total, porque cada byte cruza la red.
- Un objeto en una clase de almacenamiento de archivo debe restaurarse antes de
  poder leerse.
