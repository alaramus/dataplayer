# Bybit

Los datos de mercado públicos de Bybit: spot, futuros USDT y USDC y futuros
inversos. Ves el último día y las reglas de cada símbolo, lees sus velas, sus
operaciones más recientes y su libro de órdenes como filas, y sigues su
mercado en directo. No se cambia nada en Bybit y no hace falta ninguna clave.
Cómo funcionan las conexiones en general se explica en la página
[Conexiones](connections.md).

## Qué puedes ver

- Spot, futuros USDT y USDC, futuros inversos, símbolos por moneda de cotización
- Las últimas 24 horas de cada símbolo: precio, cambio, máximo, mínimo, volumen
- Las reglas de cada símbolo: paso de precio, paso de cantidad, orden mínima
- Las velas de un símbolo de cualquier intervalo, de un minuto a un mes
- Las operaciones más recientes de un símbolo: 60 en spot, 1.000 en futuros
- El libro de órdenes de un símbolo, compras y ventas con su acumulado
- El mercado de un símbolo en directo: gráfico, libro y operaciones
- Cualquiera de ellos descargado como archivo
- El reloj de Bybit y cuánto del límite de solicitudes se ha usado
- El límite de solicitudes y las respuestas de Bybit en un panel
- Símbolos encontrados por nombre o por activo
- Operaciones o velas de un símbolo en un pipeline, solo lo nuevo cada vez

## Qué puedes cambiar

- Nada: los datos de mercado solo se leen

## Conexión

La página **Conexión** de la ventana pide el **Punto de acceso**:

- **Bybit** — `api.bybit.com`, y sus flujos en `stream.bybit.com`;
- **Bybit, a través de bytick.com** — el mismo servicio con su segundo
  nombre, para una red que no alcanza el primero;
- **Testnet** — la red de pruebas de Bybit, con precios propios.

Bybit no da servicio a algunos países, entre ellos Estados Unidos. Si la
comprobación dice que Bybit no da servicio a esta región o rechaza esta
dirección, el servidor de DataPlayer está en uno de ellos, y otro punto de
acceso no ayudará.

## El catálogo

- Primero **Bolsa**: lo que Bybit y esta conexión dicen de sí mismos.
- **Mercados**: una carpeta por mercado con sus símbolos. Una fila abre su
  gráfico de **Mercado** al instante.
- **Spot**, **Futuros USDT y USDC** y **Futuros inversos**. Cada uno tiene
  **Tickers**, **Símbolos** y una carpeta por moneda de cotización, la que
  tiene más símbolos primero.
- Una moneda de cotización tiene sus símbolos, solo los que cotizan ahora.
  Los futuros con fecha llevan su entrega en el nombre, como
  `BTCUSDT-27NOV26`.
- Un símbolo tiene **Mercado**, **Velas** con una serie por intervalo,
  **Operaciones** y **Libro de órdenes**.

## Mercado

**Mercado**, el primer nodo de cada símbolo, abre una pestaña que se mueve
con el mercado: el día arriba, las velas sobre su volumen, el libro con la
profundidad de cada nivel y las operaciones según ocurren.

- Elige el intervalo de las velas arriba; desplaza o arrastra el gráfico para
  mirar atrás.
- Tras el primer instante todo llega por los flujos de Bybit, que no gastan
  nada del límite de solicitudes. Varias pestañas de un símbolo comparten un
  flujo.
- Si la red cae, la pestaña lo dice y vuelve sola.

## Tablas

- **Tickers**: una fila por símbolo, los de más volumen cotizado primero.
  Cada columna ordena y filtra. Se actualiza cada diez segundos.
- **Símbolos**: una fila por símbolo con sus reglas. Los futuros añaden el
  tipo de contrato de Bybit, la fecha de entrega de un futuro con fecha y
  cuándo empezó a cotizar.
- **Velas**: las más recientes primero; ordena por **open_time** para empezar
  por las más antiguas, y filtra por él para elegir dónde empieza y acaba la
  lectura. La vela aún abierta dice `closed` false.
- **Operaciones**: solo las más recientes que da Bybit — 60 en spot, 1.000 en
  futuros, menos de un minuto en un símbolo activo. Cada columna ordena y
  filtra. Bybit no da operaciones más antiguas.
- **Libro de órdenes**: compras de la mejor a la peor, luego ventas. Un
  filtro en **level** elige la profundidad, hasta 1.000; 100 niveles por
  defecto. Un filtro en **side** deja un lado.
- **volume** está siempre en el activo base y **quote_volume** en la moneda
  de cotización. Los futuros inversos cuentan en USD, y DataPlayer pone cada
  uno en su sitio.
- Precios y cantidades son decimales exactos, tal como los escribe Bybit.

## En un pipeline

Las **Operaciones** de un símbolo y cada serie de **Velas** pueden iniciar un
enlace de pipeline que sigue leyendo: **Añadir mensajes nuevos a una tabla**
o **a una tabla nueva**, o **Mantener el último por clave**. Cada ejecución
lee solo lo llegado desde la anterior, y un pipeline encendido lo lleva en
segundos.

- DataPlayer guarda dónde se detuvo cada enlace; Bybit no.
- **La primera ejecución lee**: **Solo lo nuevo** empieza ahora; **Desde lo
  más antiguo disponible** empieza por las operaciones que Bybit aún da, o el
  último día de velas.
- Una vela se lee cuando ha cerrado.
- Bybit da solo sus operaciones más recientes, así que un enlace que se
  ejecuta con menos frecuencia de la que un símbolo activo hace mil
  operaciones pierde algunas; la ejecución dice que se saltaron operaciones.
  Enciende el pipeline para llevarlas según llegan.
- Una tabla que crea el enlace tiene por clave el **id** de la operación o el
  **open_time** de la vela, así que nada llega dos veces.

## Bolsa

- **Estado**: el punto de acceso y si cada mercado responde.
- **Reloj**: la hora de cada mercado y cuánto adelanta al servidor de
  DataPlayer.
- **Límite de solicitudes**: lo que Bybit permite a esta dirección en cinco
  segundos, lo usado, dónde se detiene DataPlayer y si hay solicitudes
  retenidas.
- **Mercados**: cuántos símbolos cotizan, en cuántas monedas de cotización y
  cuándo se leyó la lista; se vuelve a leer tras una hora.

## Paneles y búsqueda

- El panel **Conexión Bybit** dibuja las solicitudes de cada cinco segundos
  frente al tope de DataPlayer, cuánto tarda Bybit en responder y si cada
  mercado responde. Los precios no están: llévalos a una tabla con un
  pipeline y dibújala.
- La búsqueda encuentra símbolos por nombre y por activo: `btc` encuentra
  BTCUSDT y ETHBTC, los nombres primero. Buscar dentro de una moneda de
  cotización se queda en ella. Los símbolos pueden guardarse para la búsqueda
  en todo.

## El límite de solicitudes

Bybit permite a una dirección 600 solicitudes en cinco segundos entre todos
sus mercados, y bloquea al menos diez minutos a una dirección que pide más.
DataPlayer cuenta sus propias solicitudes y se detiene en 240 en cinco
segundos, diciendo cuánto esperar. Si Bybit bloquea la dirección de todos
modos, no se pide nada hasta que acaba el bloqueo.
