# Correo electrónico

Tu buzón en DataPlayer: carpetas, mensajes, respuestas y adjuntos, en una
pestaña propia en lugar de un catálogo. Cómo funcionan las conexiones en
general está en la página [Conexiones](connections.md).

## Qué puedes ver

- Las carpetas del buzón, con cuántos mensajes y cuántos sin leer tiene cada una
- Los mensajes de una carpeta, los más nuevos primero, de cincuenta en cincuenta
- Mensajes encontrados por palabras del remitente, el asunto o el texto
- Un mensaje: de quién, para quién, su texto y sus adjuntos
- Las imágenes de la web de un mensaje, cuando las pides
- Un aviso cuando llegan mensajes nuevos a Recibidos

## Qué puedes cambiar

- Mensajes nuevos, respuestas, respuestas a todos y reenvíos con sus archivos
- Mensajes marcados como leídos o no leídos
- Mensajes movidos a la papelera y eliminados de ella para siempre
- Adjuntos guardados en tu equipo o en tu propia carpeta
- Borradores guardados, terminados más tarde y enviados
- El texto del mensaje se dicta con el micrófono junto al campo: se inserta donde está el cursor y se corrige allí mientras se reconoce; después de escribir, el dictado continúa desde el nuevo cursor
- Mensajes movidos a otra carpeta
- Archivos de tu propia carpeta adjuntos a un mensaje

## Conexión

La página **Conexión** pide la **Dirección de correo** y **Su nombre**, el
**Usuario** (vacío para la dirección) y la **Contraseña** —para Gmail, Yandex
o Mail.ru, una contraseña de aplicación—, el **Servidor IMAP**, el **Puerto
IMAP** y la **Seguridad IMAP** (`tls` 993, `starttls` 143, `none` solo dentro
de tu red), el **Servidor SMTP**, el **Puerto SMTP** y la **Seguridad SMTP**
(`tls` 465, `starttls` 587), el **Inicio de sesión SMTP** y si se debe
**Guardar una copia en Enviados** —desactivado para Gmail, que la guarda solo.

**Comprobar** dice qué paso falló. Con `starttls`, un servidor que no cifra se
rechaza en lugar de recibir la contraseña en claro.

## La pestaña Correo

A la izquierda las carpetas, en el centro los mensajes, a la derecha el
mensaje abierto. Abrir un mensaje lo marca como leído. Un mensaje en forma de
página web se muestra sin scripts, y las imágenes de la web solo tras
**Mostrar imágenes**. **Eliminar** mueve a la papelera; en la papelera elimina
para siempre después de preguntar. Un adjunto se puede **Descargar** o
**Guardar en mi carpeta** —en `Mail/<dirección>/`, sin sobrescribir nada y
dentro del límite de tu almacenamiento. Adjuntos de un mensaje nuevo: 25 MB en
total.

## Quién puede abrirlo

Solo tú. Quien recibe la conexión compartida la ve, pero no puede abrir el
buzón. La búsqueda de arriba y el agente no leen el correo.

## Novedades de este buzón

El catálogo tiene dos tarjetas: **Correo electrónico** para cualquier servidor, y **Gmail**, que rellena sus servidores. Gmail necesita una contraseña de aplicación; Microsoft 365 y Outlook.com rechazan una contraseña por IMAP y aún no se ofrecen.

Mientras tienes la sesión abierta, Recibidos se consulta más o menos una vez por minuto; los mensajes nuevos se anuncian con **Abrir**. **Mover a una carpeta** mueve el mensaje abierto. **Desde mi carpeta** adjunta archivos de tu almacenamiento. **Guardar borrador** deja el mensaje en Borradores; **Editar** lo retoma.

## Lo que el correo aún no hace aquí

- Avisar de mensajes nuevos en carpetas que no sean Recibidos
- Marcas, firmas, arrastrar un mensaje a una carpeta
- Gmail y Microsoft 365 sin contraseña de aplicación, Exchange sin IMAP, túnel SSH
