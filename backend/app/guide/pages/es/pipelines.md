# Flujos

Un flujo dispone sus conexiones en un lienzo y traza enlaces entre lo que contienen: filas de una tabla copiadas a otra tabla, una tabla guardada como archivo CSV en una carpeta, un tema leído en una tabla, etc. Un flujo se ejecuta cuando pulsa **Ejecutar**, según un horario o —para un enlace que lee un tema o una cola— de forma continua.

Los flujos están en el espacio **Flujos** del interruptor de la parte superior de la barra izquierda. Un flujo es solo suyo: no se comparte.

## Crear un flujo

1. **Crear un flujo**, o **Nuevo** junto al selector de flujos en la cabecera. Se le pone un nombre por defecto; el lápiz lo renombra.
2. Arrastre una conexión desde la lista de la izquierda hasta el lienzo, o púlsela. Se abre una ventana de su catálogo con casillas.
3. Marque lo que el flujo toma de la conexión — tablas, archivos, temas, claves — o un lugar donde llegarán las cosas: un esquema, una carpeta, la raíz de su almacenamiento. Las casillas se conservan al entrar en otro nivel.
4. **Colocar en el lienzo**. Lo marcado se convierte en una tarjeta: la conexión en su cabecera y una fila por cada elemento marcado.

Una conexión puede tener varias tarjetas. Una tarjeta se mueve a mano. El engranaje de su cabecera, o un doble clic, vuelve a abrir la ventana para cambiar lo que contiene; su cruz la quita del flujo. La conexión en sí no cambia.

Una tarjeta cuya conexión ya no existe, ya no se comparte con usted o está desactivada aparece con línea discontinua y lo indica. Una tabla que ya no existe aparece tachada como «not found».

## Enlaces

- Arrastre una fila de una tarjeta sobre una fila de otra. Si algo puede pasar de una a otra, se dibuja un enlace; si no, se indica por qué.
- **Mostrar los enlaces que se podrían dibujar**, en la cabecera, dibuja con línea discontinua cada enlace posible entre las filas del lienzo, con una etiqueta de lo que haría. Pulsar un enlace discontinuo lo dibuja.
- Los dos extremos de un enlace deben estar en conexiones distintas: dentro de una misma conexión, use **Copiar** y **Pegar** en su catálogo.

Al seleccionar un enlace se abre su panel bajo el lienzo: qué hace, una elección de **Operación** cuando encajan varias, y las opciones propias de esa operación — un **Nombre del archivo** y qué hacer **Si el nombre ya está ocupado** (**Detener y avisar**, **Conservar ambos**, **Reemplazarlo**), la tabla en la que escribir y cómo se emparejan sus columnas con las filas, o las columnas de **Una tabla nueva**. Un enlace que escribe en claves de Redis se configura en **Clave y valores**: qué columna nombra cada clave, qué se antepone y cuánto vive una clave.

Cada enlace recibe un número en el orden en que se ejecuta. Un enlace espera a todos los enlaces que escriben en la tarjeta de la que lee.

## Ejecutar

- **Ejecutar** guarda el flujo y ejecuta cada enlace, uno tras otro. Se niega a empezar antes de ejecutar nada si a un enlace le falta alguna elección, y abre ese enlace.
- El primer enlace que falla detiene la ejecución; los enlaces siguientes no se ejecutan.
- Mientras se ejecuta, cada enlace muestra **Esperando**, **En ejecución**, **Listo** o **Fallido**, y la ejecución aparece en la campana de actividad, donde puede detenerse. Detenerla termina el enlace en curso; los siguientes no se ejecutan.
- Lo que pasa por un enlace se ejecuta con su acceso en ese momento. Una conexión a la que ya no puede llegar hace fallar su enlace.

## Horario

El reloj de la cabecera abre **Programación**: **Ejecutar por sí solo**, y luego **Cada cierto tiempo** — un número de minutos, horas o días — o **A horas del día**, en los días marcados. Las horas son las del reloj del navegador que guardó el horario. La cabecera muestra la próxima ejecución.

## Seguir un tema o una cola

Un enlace que lee un tema de Kafka, un flujo o cola de RabbitMQ, u otra fuente de mensajes, puede marcarse como **Seguir** en su panel. **La primera ejecución lee** elige **Desde lo más antiguo disponible** o **Solo lo nuevo**; después, el enlace sigue leyendo desde donde se detuvo.

El interruptor **Seguir** de la cabecera transporta entonces lo que llega en segundos, hasta que se apaga. Mientras sigue, la campana de actividad indica cuántos mensajes se han transportado, y un enlace que falla sin parar aparece en **Requiere tu atención**.

## Historial

**Historial**, en la cabecera, enumera cada ejecución, la más reciente primero: cuándo empezó, si fue a mano o por el horario, cuánto duró y qué hizo cada enlace. Elegir una ejecución la muestra en el lienzo; **Volver a la última ejecución** vuelve.

## Límites

- 100 flujos por persona, 50 tarjetas por flujo, 100 filas por tarjeta, 200 enlaces por flujo.
- Borrar un flujo elimina sus tarjetas y su historial. Nada cambia en las conexiones.
