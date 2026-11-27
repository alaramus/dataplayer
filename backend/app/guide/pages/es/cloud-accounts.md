# Cuentas en la nube

Una cuenta en la nube es la forma en que una conexión llega a una nube en su
nombre: para obtener un token con el que iniciar sesión en una base de datos o
para leer una contraseña guardada en un almacén de secretos. Es suya, como una
clave SSH: una conexión la nombra, y quien comparte la conexión con usted la usa
sin verla. Las cuentas se guardan en **Preferencias**, en **Cuentas en la
nube**; la página **Opciones** de la ventana de una conexión también tiene un
botón **Nueva cuenta**.

## Tipos

- **Amazon Web Services**: una **Clave de acceso** y su **Clave secreta**, con
  un **Token de sesión** para credenciales temporales. Puede asumir un **Rol**:
  su ARN, un **ID externo**, nombre y duración de la sesión.
- **Google Cloud**: un archivo de **Clave de cuenta de servicio** en JSON.
  Puede actuar como otra cuenta de servicio, si esta se lo permite.
- **Microsoft Azure**: una **Entidad de servicio**: inquilino, ID de cliente y
  secreto de cliente.
- **HashiCorp Vault**: su **Dirección**, un espacio de nombres y un certificado
  CA si hacen falta, y un **Token** o el Role ID y el Secret ID de **AppRole**.

Los secretos se guardan cifrados y no se vuelven a mostrar. **Probar** hace la
llamada inofensiva más barata que permite la cuenta y dice quién inició sesión.

## La identidad propia de este servidor

Una cuenta también puede iniciar sesión como la máquina donde se ejecuta
DataPlayer: la cadena de credenciales predeterminada de AWS, las Application
Default Credentials de Google, una identidad administrada de Azure. Cualquiera
podría tomar prestada esa identidad, así que solo se ofrece donde la
instalación lo permite, y entonces solo a un superusuario.

## Qué hace una conexión con ella

Se emite un token para cada conexión nueva y se guarda solo en memoria hasta
poco antes de que caduque; nada emitido se almacena. La página de cada fuente
dice qué formas de iniciar sesión usan una cuenta:

- PostgreSQL y MySQL: AWS IAM (RDS), Google Cloud IAM (Cloud SQL), Microsoft
  Entra, un almacén de secretos, credenciales dinámicas de Vault.
- Redis: AWS IAM (ElastiCache, MemoryDB), Microsoft Entra.
- MongoDB: AWS IAM (MONGODB-AWS), un almacén de secretos.
- Kafka: AWS IAM (MSK).
- S3: una cuenta de AWS en lugar de una clave.

Un **Almacén de secretos** nombra el secreto donde se guarda: en AWS por su
nombre o ARN; en Google como `projects/P/secrets/S`, o solo por su nombre en el
proyecto del archivo de clave; en Azure como `VAULT/NAME`; en Vault como
`MOUNT/PATH`. Un secreto en JSON se lee por sus claves `password` y `username`,
que pueden renombrarse; cualquier otro secreto es la contraseña misma.

Un servidor que comprueba contraseñas con LDAP, PAM, RADIUS o Active Directory
no necesita ninguna cuenta: para DataPlayer parece una contraseña.

## Límites

- Una cuenta conserva su tipo; cree una nueva para otra nube.
- No se puede eliminar una cuenta que usa una conexión; el rechazo nombra las
  conexiones.
- Un token que caduca durante una copia de seguridad larga no la detiene: la
  conexión que abrió sigue siendo válida.
- Las herramientas de Kafka en un terminal aún no pueden iniciar sesión con AWS
  IAM ni con OIDC.
