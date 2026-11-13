# Preferencias y su cuenta

**Preferencias**, en el menú de usuario de arriba a la derecha, contiene lo que le pertenece a usted y no a una sola conexión. **Cerrar sesión** está en el mismo menú.

## General

- **Idioma**: el idioma de toda la interfaz. Se guarda con su cuenta, así que lo acompaña en cualquier navegador. Hasta que se elija uno, se usa el del navegador.
- **Aspecto**: un tema claro u oscuro, o **Sistema**, que sigue al sistema operativo. Se guarda con su cuenta.
- **Voz de lectura**: la voz que lee los mensajes en voz alta. Las voces son del propio navegador, así que este ajuste se guarda en este navegador.
- **Almacenamiento personal**: cuánto de sus propios archivos en este servidor usa, frente al límite que fijó un administrador.

## Conexiones

**Con qué frecuencia se comprueban las conexiones**: cada conexión se sondea según este horario mientras hay un espacio de trabajo abierto, y el punto junto a ella en la lista indica cuál fue la última respuesta. **Nunca** comprueba solo cuando usted lo pide. Un servidor lento o lejano merece preguntarle con menos frecuencia.

## Claves SSH

Las claves con las que entran sus conexiones SSH. Más información en la página [SSH](source-ssh.md).

- **Nueva clave** crea una en este servidor, donde se queda. **Copiar la clave pública** y añádala a `authorized_keys` en los servidores que deba abrir.
- **Importar** trae una clave que ya tiene.
- Una clave puede conservar su frase de paso, no tener ninguna, o pedirla. Una que la pide está **Bloqueada** hasta que la **Desbloquear** durante 15 minutos, 1 hora u 8 horas; **Bloquearla ahora** la vuelve a bloquear.
- Una clave que usa una conexión no puede borrarse hasta que sus conexiones usen otra.

## Recorridos

El recorrido de bienvenida y recorridos breves de cada parte de DataPlayer — leer una tabla de otra forma, un flujo, cuadros de mando, el agente. **Hacer** inicia uno, **Otra vez** repite uno ya hecho. Un recorrido crea para sí mismo una base de datos de práctica y la retira al terminar.

## Acceso MCP

Los tokens con los que un agente de IA ajeno a DataPlayer, como Claude Code, Cursor o Codex, trabaja con sus conexiones. Cómo crear uno está en la página [El agente de IA](assistant.md).

## Administración

Un administrador tiene además **Administración** en el menú de usuario, con **Usuarios**:

- **Nuevo usuario** crea una cuenta. Espera una contraseña: **Enlace para establecer la contraseña** da un enlace para enviar a la persona, que funciona una vez y durante un tiempo limitado. El mismo enlace restablece una contraseña olvidada.
- **Editar esta cuenta** cambia el nombre, si la persona **Puede iniciar sesión**, si es **Administrador**, y su **Límite de almacenamiento**.
- **Eliminar esta cuenta y todo lo que posee** elimina a la persona con sus conexiones y sus archivos.

Un administrador gestiona cuentas, no los datos de otros: no ve las conexiones de otras personas.
