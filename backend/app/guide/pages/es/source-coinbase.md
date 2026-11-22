# Coinbase Exchange

Los datos de mercado públicos de Coinbase Exchange: sus productos spot. Ves
el último día y las reglas de cada producto, lees sus velas, todas sus
operaciones desde el inicio y su libro de órdenes como filas, y sigues su
mercado en directo. No se cambia nada en Coinbase y no hace falta ninguna
clave. Cómo funcionan las conexiones en general se explica en la página
[Conexiones](connections.md).

## Qué puedes ver

- Productos spot por moneda de cotización
- Las últimas 24 horas de cada producto: precio, cambio, máximo, mínimo, volumen
- Las reglas de cada producto: paso de precio, paso de cantidad, orden mínima
- Las velas de un producto: 1 y 5 minutos, 15 minutos, 1 y 6 horas, un día
- Todas las operaciones de un producto desde que cotiza, por número
- El libro de órdenes de un producto, compras y ventas con su acumulado
- El mercado de un producto en directo: gráfico, libro y operaciones
- Cualquiera de ellos descargado como archivo
- El reloj de Coinbase y cuánto del límite de solicitudes se ha usado
- El límite de solicitudes y las respuestas de Coinbase en un panel
- Productos encontrados por nombre o por activo
- Operaciones o velas de un producto en un pipeline, solo lo nuevo cada vez

## Qué puedes cambiar

- Nada: los datos de mercado solo se leen

## Lo que Coinbase Exchange aún no tiene aquí

- Tu cuenta: todavía no se pide una clave

## Conexión

La página **Conexión** de la ventana pide el **Punto de acceso**:

- **Coinbase Exchange** — `api.exchange.coinbase.com`, y su flujo en
  `ws-feed.exchange.coinbase.com`;
- **Sandbox** — el entorno de pruebas público de Coinbase, con precios
  propios.

## El catálogo

- Primero **Bolsa**: lo que Coinbase y esta conexión dicen de sí mismos.
- **Mercados**: una carpeta con todos los productos. Una fila abre su gráfico
  de **Mercado** al instante.
- **Spot** tiene **Tickers**, **Símbolos** y una carpeta por moneda de
  cotización, la que tiene más productos primero.
- Una moneda de cotización tiene sus productos, solo los que cotizan ahora,
  como `BTC-USD`.
- Un producto tiene **Mercado**, **Velas** con una serie por intervalo,
  **Operaciones** y **Libro de órdenes**.

## Mercado

**Mercado**, el primer nodo de cada producto, abre una pestaña que se mueve
con el mercado: el día arriba, las velas sobre su volumen, el libro con la
profundidad de cada nivel y las operaciones según ocurren.

- Elige el intervalo de las velas arriba; desplaza o arrastra el gráfico para
  mirar atrás.
- Tras el primer momento todo llega del flujo de Coinbase, que no cuesta nada
  del límite de solicitudes. Coinbase no envía velas en él, así que DataPlayer
  dibuja la vela aún abierta a partir de las operaciones según llegan.
- Si la red cae, la pestaña lo dice y vuelve sola.

## Tablas

- **Tickers**: una fila por producto, los de más volumen primero. Cada columna
  se ordena y se filtra. Se refresca cada diez segundos. Coinbase da el
  volumen del día solo en el activo base, así que no hay **quote_volume**.
- **Símbolos**: una fila por producto con sus reglas.
- **Velas**: las más recientes primero; ordena por **open_time** para empezar
  por las más antiguas, y filtra por él para elegir dónde empieza y termina
  la lectura. La vela aún abierta dice `closed` false. Coinbase no da vela de
  un intervalo sin operaciones.
- **Operaciones**: las más recientes primero. Coinbase numera las operaciones
  de un producto una tras otra desde la primera y las guarda todas: filtra
  por **id** para elegir dónde mirar, y ordena por **id** para empezar por la
  primera de todas. Coinbase no sabe encontrar una operación por su hora, así
  que **time** no es un filtro.
- **Libro de órdenes**: compras de la mejor a la peor, luego ventas. Un filtro
  en **level** elige la profundidad, hasta 1.000; 100 niveles por defecto. Un
  filtro en **side** deja un lado.
- **volume** está siempre en el activo base. Precios y cantidades son
  decimales exactos, tal como los escribe Coinbase.

## En un pipeline

Las **Operaciones** de un producto y cada serie de **Velas** pueden iniciar
un enlace de pipeline que sigue leyendo: **Añadir mensajes nuevos a una
tabla** o **a una tabla nueva**, o **Mantener el último por clave**. Cada
ejecución lee solo lo llegado desde la anterior, y un pipeline encendido lo
lleva en segundos.

- DataPlayer guarda dónde se detuvo cada enlace; Coinbase no.
- **La primera ejecución lee**: **Solo lo nuevo** empieza ahora; **Desde lo
  más antiguo disponible** empieza por las mil operaciones más recientes, o
  el último día de velas.
- Una vela se lee cuando ha terminado su intervalo.
- Coinbase guarda todas las operaciones, así que un enlace que lleva mucho
  sin ejecutarse no pierde ninguna.
- Una tabla que crea el enlace tiene por clave el **id** de la operación o el
  **open_time** de la vela, así que nada llega dos veces.

## Bolsa

- **Estado**: el punto de acceso y si Coinbase responde.
- **Reloj**: la hora de Coinbase y cuánto adelanta al servidor de DataPlayer.
- **Límite de solicitudes**: lo que Coinbase permite a esta dirección en un
  segundo, lo usado, dónde se detiene DataPlayer y si hay solicitudes
  retenidas.
- **Mercados**: cuántos productos cotizan, en cuántas monedas de cotización y
  cuándo se leyó la lista; se vuelve a leer tras una hora.

## Paneles y búsqueda

- El panel **Conexión Coinbase** dibuja las solicitudes de cada segundo frente
  al tope de DataPlayer, cuánto tarda Coinbase en responder y si responde. Los
  precios no están: llévalos a una tabla con un pipeline y dibújala.
- La búsqueda encuentra productos por nombre y por activo: `eth` encuentra
  ETH-USD y ETH-BTC. Buscar dentro de una moneda de cotización se queda en
  ella. Los productos pueden guardarse para la búsqueda en todo.

## El límite de solicitudes

Coinbase permite a una dirección diez solicitudes públicas por segundo.
DataPlayer cuenta sus propias solicitudes y se detiene en cuatro por segundo,
así que nunca pasa de ocho en un segundo cualquiera; una solicitud por encima
espera al segundo siguiente en vez de fallar, así que una descarga larga
tarda unos segundos más. Si Coinbase rechaza la dirección de todos modos, las
solicitudes esperan un segundo.
