"""What S3 writes, in Spanish (D226).

The file side is the explorer's and words itself; these are the words of the
store, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "S3": "S3",
    "Amazon S3 or a store that speaks its API. Browse buckets and folders and work with objects as with your own files: tables, SQL over files, the editor, archives, search and copying between connections. Buckets are made and deleted here too. Signs in with an access key.": "Amazon S3 o un almacenamiento que habla su API. Explora buckets y carpetas y trabaja con los objetos como con tus propios archivos: tablas, SQL sobre archivos, el editor, archivos comprimidos, la búsqueda y la copia entre conexiones. Aquí también se crean y eliminan buckets. Inicia sesión con una clave de acceso.",
    "The store's address, such as https://s3.example.com; empty for Amazon S3": "La dirección del almacenamiento, como https://s3.example.com; vacío para Amazon S3",
    "Region": "Región",
    "Empty is us-east-1": "Vacío es us-east-1",
    "Access key": "Clave de acceso",
    "Bucket": "Bucket",
    "Empty shows every bucket this key may list": "Vacío muestra todos los buckets que esta clave puede listar",
    "Where browsing starts inside the bucket": "Dónde empieza la navegación dentro del bucket",
    "Addressing": "Direccionamiento",
    "Auto is virtual-hosted on Amazon S3 and path-style elsewhere": "Automático es virtual-hosted en Amazon S3 y path-style en los demás",
    "Verify the certificate": "Verificar el certificado",
    "Off only for a store with a certificate of its own making": "Desactívalo solo para un almacenamiento con un certificado propio",
    "The endpoint must be an http or https address": "El punto de acceso debe ser una dirección http o https",
    "A bucket is one name, without slashes": "Un bucket es un solo nombre, sin barras",
    "The folder must stay inside the bucket": "La carpeta debe quedar dentro del bucket",
    "A folder needs the bucket it is in": "Una carpeta necesita el bucket en el que está",
    "The store does not know this access key": "El almacenamiento no conoce esta clave de acceso",
    "The secret key does not match the access key": "La clave secreta no corresponde a la clave de acceso",
    "The store does not let this key do that": "El almacenamiento no permite eso a esta clave",
    "There is no such bucket in this store": "No existe ese bucket en este almacenamiento",
    "The bucket is in another region than this connection names": "El bucket está en otra región que la que indica esta conexión",
    "This object is archived and has to be restored first": "Este objeto está archivado y primero hay que restaurarlo",
    "That is no longer in the store": "Eso ya no está en el almacenamiento",
    "The store's certificate was not accepted": "No se aceptó el certificado del almacenamiento",
    "The store did not answer in time": "El almacenamiento no respondió a tiempo",
    "Could not reach the store": "No se pudo contactar con el almacenamiento",
    "The store could not do that": "El almacenamiento no pudo hacer eso",
    "Only buckets are kept at the root of the store": "En la raíz del almacenamiento solo hay buckets",
    "{name} holds more than {count} objects; this store changes them one by one, so it is refused": "{name} contiene más de {count} objetos; este almacenamiento los cambia uno a uno, así que se rechaza",
    "The store did not delete every object": "El almacenamiento no eliminó todos los objetos",
    "A bucket is not renamed or copied as a whole": "Un bucket no se renombra ni se copia entero",
    "A bucket's name is 3 to 63 lowercase letters, digits, dots and hyphens, beginning and ending with a letter or a digit": "El nombre de un bucket tiene de 3 a 63 letras minúsculas, dígitos, puntos y guiones, y empieza y termina con una letra o un dígito",
    "{name} keeps old versions of its objects; empty it with a lifecycle rule, then delete it": "{name} guarda versiones antiguas de sus objetos; vacíalo con una regla de ciclo de vida y luego elimínalo",
}
