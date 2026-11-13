# Cuadros de mando

Un cuadro de mando dibuja métricas a lo largo del tiempo: gráficos y mosaicos sobre una cuadrícula. Las métricas llegan de los agentes que ejecuta en sus máquinas y de las conexiones que informan sobre sí mismas. Los cuadros de mando están en el espacio **Cuadros de mando** del interruptor de la parte superior de la barra izquierda.

## Antes del primer cuadro de mando

Las métricas se guardan en un almacén propio, una base de datos TimescaleDB. Un administrador lo configura una vez para toda la instalación: el espacio Dashboards ofrece iniciarlo aquí o conectar uno existente. Hasta entonces, a los demás se les indica que lo configura un administrador.

**El almacén de métricas**, en la cabecera de la barra, es del administrador: dónde está el almacén, cuánto ocupa, cuánto tiempo guarda cada cosa y cómo eliminarlo. Las muestras brutas se guardan una semana; los promedios de cinco minutos y de una hora se guardan más tiempo.

## De dónde llegan las métricas

**Fuentes**, en la cabecera de la barra, abre una ventana con dos vistas.

- **Agentes**: un agente es un pequeño programa que informa de la máquina en la que se ejecuta, por ejemplo sus procesadores, su memoria y sus procesos. Escriba un **Nombre del agente** y pulse **Registrar**: la ventana muestra la clave del agente y un archivo de Docker Compose que lo inicia con esa clave en la máquina que se quiere vigilar. **Hosts** enumera lo que informan sus agentes, con el sistema, el hardware, el tiempo que lleva encendido cada uno y cuándo se oyó por última vez. **Emitir una clave nueva** invalida la clave anterior; eliminar un agente descarta desde entonces todo lo que envía.
- **Conexiones**: una conexión PostgreSQL, MySQL o Redis puede informar de sus propios contadores. Su propietario activa **Informes** y elige **Con qué frecuencia**, de cada 15 segundos a cada 5 minutos. Cualquiera con quien se comparta la conexión puede dibujar lo que informa.

Lo que envía un agente aparece en los gráficos abiertos en un par de segundos.

## Crear un cuadro de mando

1. **Nuevo cuadro de mando** en la cabecera de la barra. Se le pone un nombre por defecto; renómbrelo desde su cabecera.
2. **Añadir widgets** abre las fuentes como un árbol. Marque las series que quiere dibujar y pulse **Añadir**. Al elegir un host o una conexión se ofrecen sus disposiciones ya preparadas — **Host Linux**, **Base de datos PostgreSQL**, **Servidor MySQL**, **Servidor Redis** — y **Añadir diseño** coloca una bajo lo que el cuadro de mando ya contiene.
3. Mueva un widget por su cabecera, redimensiónelo por su esquina y haga doble clic en su título para renombrarlo. El `processes` de un host crea una tabla de sus procesos, ordenable por CPU, memoria o PID.

El cuadro de mando se guarda un momento después de cada cambio. **Intervalo** elige hasta dónde atrás dibujar, desde los últimos 5 minutos hasta los últimos 30 días, y **Actualizar cada** cada cuánto volver a leer.

Un widget puede ocupar todo el cuadro de mando (**Llenar el cuadro de mando con este widget**), o abrirse en una ventana que se mantiene al volver a Data.

## Compartir un cuadro de mando

**Compartir este cuadro de mando** da acceso a una persona: **Puede ver** o **Puede editar**. La encuentra en **Compartidos contigo**, en la barra. Quien recibe acceso ve todas las series del cuadro de mando, incluidos los hosts de sus agentes, y nada más de sus datos. Quien solo puede ver puede elegir otro rango para sí; nada de lo que hace se guarda.

La ventana también tiene el enlace del cuadro de mando. Abre el cuadro de mando para cualquiera a quien se haya dado acceso, y para nadie más.

## Límites

- Borrar un cuadro de mando elimina sus widgets; las métricas se mantienen.
- Un host que se reinicia sin parar aparece en **Requiere tu atención** en la campana de actividad.
