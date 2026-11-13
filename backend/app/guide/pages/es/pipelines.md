# Flujos

Un flujo dispone sus conexiones en un lienzo y traza enlaces entre lo que contienen: filas de una tabla copiadas en otra tabla, una tabla guardada como archivo CSV en una carpeta, un tema leído de forma continua en una tabla, etc. Encendido, funciona solo: un enlace que lee un tema, una cola o un flujo de mensajes lleva lo que llega en segundos, y los demás enlaces se ejecutan según la programación. También puede ejecutarse una vez a mano.

Los flujos están en el espacio **Flujos** del interruptor de la parte superior de la barra izquierda. Un flujo es solo suyo: no se comparte.

## Crear un flujo

1. **Crear un flujo**, o **Nuevo** junto al selector de flujos en la cabecera. Se le pone un nombre por defecto; el lápiz lo renombra.
2. Arrastre una conexión desde la lista de la izquierda hasta el lienzo, o púlsela. Se abre una ventana de su catálogo con casillas.
3. Marque lo que el flujo toma de la conexión — tablas, archivos, temas, claves — o un lugar donde llegarán las cosas: un esquema, una carpeta, la raíz de su almacenamiento. Las casillas se conservan al entrar en otro nivel.
4. **Colocar en el lienzo**. Lo marcado se convierte en una tarjeta: la conexión en su cabecera y una fila por cada elemento marcado.

Una conexión puede tener varias tarjetas. Una tarjeta se mueve a mano. El engranaje de su cabecera, o un doble clic, vuelve a abrir la ventana para cambiar lo que contiene; su cruz la quita del flujo. La conexión en sí no cambia.

Una tarjeta cuya conexión ya no existe, ya no se comparte con usted o está desactivada aparece con línea discontinua y lo indica. Una tabla que ya no existe aparece tachada como «not found».

## Enlaces

- Arrastre una fila de una tarjeta sobre una fila de otra. Mientras arrastra, cada fila a la que puede ir se tiñe y dice qué haría soltarla allí; las demás se atenúan y dicen por qué no. Al soltarla sobre una fila teñida se traza el enlace.
- Un enlace se traza listo para ejecutarse cuando sus opciones pueden deducirse: una tabla nueva se llama como su origen y recibe todas sus columnas, las columnas se emparejan por nombre, las claves salen de la clave de un tema. Su panel cambia cualquiera de ellas.
- Un enlace al que aún le falta una elección se traza en el color de advertencia y dice qué necesita. La línea bajo el lienzo lo nombra, y **Elegir** lo abre.
- Los dos extremos de un enlace deben estar en conexiones distintas: dentro de una misma conexión, use **Copiar** y **Pegar** en su catálogo.

Al seleccionar un enlace se abre su panel bajo el lienzo: qué hace, una elección de **Operación** cuando encajan varias, y las opciones propias de esa operación — un **Nombre del archivo** y qué hacer **Si el nombre ya está ocupado** (**Detener y avisar**, **Conservar ambos**, **Reemplazarlo**), la tabla en la que escribir y cómo se emparejan sus columnas con las filas, o las columnas de **Una tabla nueva**. Un enlace que escribe en claves de Redis se configura en **Clave y valores**: qué columna nombra cada clave, qué se antepone y cuánto vive una clave.

Cada enlace recibe un número en el orden en que se ejecuta. Un enlace espera a todos los enlaces que escriben en la tarjeta de la que lee.

## Encender

**Encender**, en la cabecera, guarda el flujo y lo pone en marcha. Un enlace que lee un tema, una cola o un flujo de mensajes se ejecuta de forma continua: lleva lo que llega en segundos. Todos los demás enlaces se ejecutan según la programación. **Apagar** detiene ambos.

- Encender se niega antes de que empiece nada si a un enlace le falta una elección, y abre ese enlace; si hay enlaces que se ejecutan según la programación y no hay ninguna, abre **Programación…**.
- La línea bajo el lienzo dice qué le falta al flujo o qué hace: qué hará al encenderlo, cuánto lleva encendido y cuándo llevó algo por última vez, cuándo llega la próxima ejecución programada, o qué enlace falla sin parar.
- Un enlace que lee de forma continua puede ejecutarse según la programación: **Mientras el flujo está encendido** en su panel. **La primera ejecución lee** elige **Desde lo más antiguo disponible** o **Solo lo nuevo**; después, el enlace sigue leyendo desde donde se detuvo.
- Mientras está encendido, la campana de actividad indica cuántos mensajes se han llevado, y un enlace que falla sin parar aparece en **Requiere tu atención**. Detenerlo allí apaga el flujo.

## Ejecutar una vez

- **Ejecutar una vez ahora**, en el menú junto a **Encender**, guarda el flujo y ejecuta cada enlace una vez, uno tras otro. Se niega antes de ejecutar nada si a un enlace aún le falta una elección, y abre ese enlace. Mientras el flujo está encendido, los enlaces que se ejecutan de forma continua quedan fuera.
- El primer enlace que falla detiene la ejecución; los enlaces siguientes no se ejecutan.
- Mientras se ejecuta, cada enlace muestra **Esperando**, **En ejecución**, **Listo** o **Fallido**, y la ejecución aparece en la campana de actividad, donde puede detenerse. Detenerla termina el enlace en curso; los siguientes no se ejecutan.
- Lo que pasa por un enlace se ejecuta con su acceso en ese momento. Una conexión a la que ya no puede llegar hace fallar su enlace.

## Horario

**Programación…**, en el menú junto a **Encender**, fija cuándo se ejecutan los enlaces programados mientras el flujo está encendido: **Cada cierto tiempo** — un número de minutos, horas o días — o **A horas del día**, en los días marcados. Las horas son las del reloj del navegador que guardó la programación. La línea bajo el lienzo muestra la próxima ejecución.

## Historial

**Historial**, en el menú **⋯** de la cabecera, enumera cada ejecución, de la más reciente a la más antigua: cuándo empezó, si a mano o por la programación, cuánto duró y qué hizo cada enlace. Elegir una ejecución la muestra en el lienzo; **Volver a la última ejecución** regresa.

## Límites

- 100 flujos por persona, 50 tarjetas por flujo, 100 filas por tarjeta, 200 enlaces por flujo.
- Borrar un flujo elimina sus tarjetas y su historial. Nada cambia en las conexiones.
