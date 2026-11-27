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

## Qué puedes cambiar

- Objetos en un editor de texto
- Las filas y columnas de archivos CSV y TSV
- Objetos y carpetas: crear, subir, renombrar, eliminar, descargar
- Archivos comprimidos: empaquetar objetos en uno o desempaquetar uno
- Objetos copiados o movidos entre carpetas y conexiones
- Buckets: crear uno, o eliminar uno con lo que contiene

## Conectar

La página **Conexión** de la ventana pide:

- **Punto de acceso**: la dirección del almacenamiento, como
  `https://s3.example.com`. Vacío es Amazon S3;
- **Región**: se elige de la lista que da Amazon, o se escribe cuando un
  endpoint nombra otro almacén; vacío es `us-east-1`;
- **Clave de acceso** y **Clave secreta**;
- **Bucket**: vacío muestra todos los buckets que la clave puede listar;
- **Carpeta**: dónde empieza la navegación dentro del bucket;
- **Direccionamiento**: «auto» es virtual-hosted en Amazon S3 y path-style en
  los demás, que todo almacenamiento compatible acepta;
- **Verificar el certificado**: desactívalo solo para un almacenamiento cuyo
  certificado hiciste tú.

**Cuenta de AWS** inicia sesión con una de sus [cuentas en la nube](cloud-accounts.md) en lugar de una clave: un token de sesión, un rol que asume o las credenciales de este servidor son de la cuenta.

**URL** muestra dónde está el almacén: su punto de acceso, o la dirección de
Amazon S3 en la región. Una dirección pegada ahí rellena el punto de acceso, y
una URL de Amazon S3 también la región; `s3://reports/2026` rellena el bucket y
la carpeta. El bucket y la carpeta no se repiten en la URL, y las claves nunca
forman parte de ella.

El catálogo de tipos muestra una tarjeta por proveedor: Amazon S3, MinIO,
RustFS, Cloudflare R2, Backblaze B2, Wasabi, DigitalOcean Spaces, Google Cloud
Storage, Yandex Object Storage, VK Cloud, Selectel y Hetzner Object Storage.
Cada tarjeta es este mismo formulario: rellena lo que el proveedor siempre
nombra igual y dice dónde encontrar el resto. Ninguna inicia un servidor.

## El catálogo y los objetos

Una conexión S3 se explora como una conexión [Archivos](source-file.md): el
mismo catálogo, la misma búsqueda por nombre y dentro de los archivos, los mismos
visores y el mismo SQL sobre archivos. También las mismas acciones: **Nueva carpeta**, **Nuevo archivo**,
**Subir archivos**, **Renombrar**, **Eliminar**, **Descargar**, **Archivar**,
**Extraer**, **Copiar**, **Cortar** y **Pegar**.

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
- Renombrar o mover una carpeta copia cada objeto que contiene y elimina los
  antiguos: el almacenamiento no sabe renombrar. Se mueven, copian o eliminan
  hasta 10.000 objetos de una vez; una carpeta mayor se rechaza.
- Un archivo que cambió mientras tanto no se sobrescribe: el guardado se
  rechaza.

### Buckets

Cuando **Bucket** está vacío, el nivel superior del catálogo lista los
buckets.

- **Nuevo bucket** allí crea un bucket, en la región de la conexión. Su nombre
  tiene de 3 a 63 letras minúsculas, dígitos, puntos y guiones, y empieza y
  termina con una letra o un dígito.
- **Eliminar** quita un bucket con todo lo que contiene, hasta 10.000 objetos.
  Un bucket que guarda versiones antiguas de sus objetos se rechaza: vacíalo
  antes con una regla de ciclo de vida.
- Un bucket no se puede renombrar: el almacén no tiene esa operación.
  **Copiar** o **Cortar** un bucket y **Pegarlo** en una carpeta de otro bucket
  deja allí sus objetos en una carpeta con su nombre; un bucket cortado se
  elimina cuando queda vacío.
- Arriba solo hay buckets, así que nuevo archivo, subir archivos y pegar no se
  ofrecen allí. Un bucket tiene un icono propio.
