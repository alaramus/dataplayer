# OKX

Los datos de mercado públicos de OKX: spot, futuros USDT y USDC y futuros
inversos, perpetuos y con vencimiento. Ves el último día y las reglas de cada
símbolo, lees sus velas, sus operaciones de los últimos tres meses y su libro
de órdenes como filas, y sigues su mercado en directo. No se cambia nada en
OKX y no hace falta ninguna clave. Cómo funcionan las conexiones en general
se explica en la página [Conexiones](connections.md).

## Qué puedes ver

- Spot, futuros USDT y USDC, futuros inversos, símbolos por moneda de cotización
- Las últimas 24 horas de cada símbolo: precio, cambio, máximo, mínimo, volumen
- Las reglas de cada símbolo: paso de precio y paso de cantidad
- Las velas de un símbolo de cualquier intervalo, de un segundo a un mes
- Las operaciones de un símbolo de los últimos tres meses, por número o fecha
- El libro de órdenes de un símbolo, compras y ventas con su acumulado
- El mercado de un símbolo en directo: gráfico, libro y operaciones
- Cualquiera de ellos descargado como archivo
- El reloj de OKX, su mantenimiento y cuánto de cada límite se ha usado
- Los límites y las respuestas de OKX en un panel
- Símbolos encontrados por nombre o por activo
- Operaciones o velas de un símbolo en un pipeline, solo lo nuevo cada vez
- Con clave: saldos, posiciones, órdenes, operaciones, depósitos y retiros

## Qué puedes cambiar

- Nada: los datos de mercado solo se leen

## Conexión

La página **Conexión** de la ventana pide el **Punto de acceso**:

- **OKX** — `www.okx.com`, y sus flujos en `ws.okx.com`;
- **OKX Europe** — `eea.okx.com`, el servicio europeo de OKX: un mercado
  aparte, con precios y operaciones propios;
- **Trading de demostración** — el mercado de demostración de OKX, con
  precios propios.
- **OKX, con una clave de API**, **OKX Europe, con una clave de API** y
  **Trading de demostración, con una clave de API** — lo mismo y además la
  cuenta a la que pertenece la clave. Piden la clave, su secreto y la frase
  de contraseña elegida al crearla.

OKX no da servicio a algunos países, entre ellos Estados Unidos. Si la
comprobación dice que OKX no da servicio a esta dirección o región, el
servidor de DataPlayer está en uno de ellos; OKX Europe solo da servicio al
Espacio Económico Europeo.

## El catálogo

- Primero **Bolsa**: lo que OKX y esta conexión dicen de sí mismos.
- **Mercados**: una carpeta por mercado con sus símbolos. Una fila abre su
  gráfico de **Mercado** al instante.
- **Spot**, **Futuros USDT y USDC** y **Futuros inversos**. Los futuros reúnen
  los swaps perpetuos y los futuros con fecha de OKX. Cada mercado tiene
  **Tickers**, **Símbolos** y una carpeta por moneda de cotización, la que
  tiene más símbolos primero.
- Una moneda de cotización tiene sus símbolos, solo los que cotizan ahora. Un
  perpetuo termina en `-SWAP`, como `BTC-USDT-SWAP`; uno con fecha en su
  fecha, como `BTC-USDT-261225`.
- Un símbolo tiene **Mercado**, **Velas** con una serie por intervalo,
  **Operaciones** y **Libro de órdenes**.

## Mercado

**Mercado**, el primer nodo de cada símbolo, abre una pestaña que se mueve
con el mercado: el día arriba, las velas sobre su volumen, el libro con la
profundidad de cada nivel y las operaciones según ocurren.

- Elige el intervalo de las velas arriba; desplaza o arrastra el gráfico para
  mirar atrás.
- Tras el primer momento todo llega de los flujos de OKX, que no cuestan nada
  de sus límites. Varias pestañas de un símbolo los comparten.
- Si la red cae, la pestaña lo dice y vuelve sola.

## Tablas

- **Tickers**: una fila por símbolo, los más activos primero. Cada columna se
  ordena y se filtra. Se refresca cada diez segundos. OKX no da volumen en la
  moneda de cotización para los futuros USDT y USDC, así que allí falta la
  columna y los más activos son los de más volumen en la moneda.
- **Símbolos**: una fila por símbolo con sus reglas. Los futuros añaden el
  tipo de OKX — `SWAP` para un perpetuo, `FUTURES` para uno con fecha —, la
  entrega de uno con fecha y cuándo se listó. Los futuros inversos añaden lo
  que vale un contrato en USD.
- **Velas**: las más recientes primero; ordena por **open_time** para empezar
  por las más antiguas, y filtra por él para elegir dónde empieza y termina
  la lectura. La vela aún abierta dice `closed` false. Días y semanas abren a
  medianoche UTC.
- **Operaciones**: las más recientes primero. OKX numera las operaciones de
  un símbolo una tras otra y las guarda tres meses: filtra por **id** o
  **time** para elegir dónde mirar, y ordena por **id** para empezar por las
  más antiguas.
- **Libro de órdenes**: compras de la mejor a la peor, luego ventas. Un
  filtro en **level** elige la profundidad, hasta 400; 100 niveles por
  defecto. Un filtro en **side** deja un lado.
- **volume** está siempre en el activo base y **quote_volume** en la moneda
  de cotización. OKX cuenta los futuros en contratos; DataPlayer dice cada uno
  por lo que vale. En los futuros inversos el tamaño de una operación está en
  USD, así que allí la columna es **quote_quantity**, y la cantidad del libro
  también está en USD.
- Precios y cantidades son decimales exactos, tal como los escribe OKX.

## En un pipeline

Las **Operaciones** de un símbolo y cada serie de **Velas** pueden iniciar un
enlace de pipeline que sigue leyendo: **Añadir mensajes nuevos a una tabla**
o **a una tabla nueva**, o **Mantener el último por clave**. Cada ejecución
lee solo lo llegado desde la anterior, y un pipeline encendido lo lleva en
segundos.

- DataPlayer guarda dónde se detuvo cada enlace; OKX no.
- **La primera ejecución lee**: **Solo lo nuevo** empieza ahora; **Desde lo
  más antiguo disponible** empieza por la última hora de operaciones, o el
  último día de velas.
- Una vela se lee cuando ha cerrado.
- Un enlace que no se ha ejecutado en más de tres meses encuentra sus
  operaciones más antiguas ya borradas de OKX; la ejecución dice cuántas se
  saltaron.
- Una tabla que crea el enlace tiene por clave el **id** de la operación o el
  **open_time** de la vela, así que nada llega dos veces.

## Tu cuenta

Con una clave, cada mercado contiene **Cuenta**: **Saldos** de la cuenta de
trading, los mismos en cada mercado; **Posiciones** en futuros; **Órdenes
abiertas**; y en spot **Depósitos** y **Retiros**. Un símbolo añade **Mis
órdenes** de los últimos siete días y **Mis operaciones** de los últimos
tres. **Mis operaciones** pueden iniciar un enlace de pipeline, como
**Operaciones**.

- Crea la clave en OKX solo con el permiso **Read**. Una clave que también
  puede operar o retirar se acepta y la comprobación lo dice: DataPlayer solo
  lee, pero una clave de solo lectura es más segura.
- Si la clave está limitada a direcciones, añade la del servidor de
  DataPlayer.
- **Clave de API** en **Bolsa** dice lo que OKX permite a la clave.

## Bolsa

- **Estado**: el punto de acceso, si OKX anuncia un mantenimiento del trading
  y si cada mercado responde.
- **Reloj**: la hora de cada mercado y cuánto adelanta al servidor de
  DataPlayer.
- **Límite de solicitudes**: para cada clase de solicitud hecha hasta ahora,
  lo que OKX permite en su ventana, lo usado, dónde se detiene DataPlayer y
  si hay solicitudes retenidas.
- **Mercados**: cuántos símbolos cotizan, en cuántas monedas de cotización y
  cuándo se leyó la lista; se vuelve a leer tras una hora.
- **Clave de API**: si la clave es de solo lectura, si puede operar o
  retirar y si está limitada a direcciones.

## Paneles y búsqueda

- El panel **Conexión OKX** dibuja las solicitudes de cada clase en su
  ventana frente al tope de DataPlayer, cuánto tarda OKX en responder y si
  cada mercado responde. Los precios no están: llévalos a una tabla con un
  pipeline y dibújala.
- La búsqueda encuentra símbolos por nombre y por activo: `btc` encuentra
  BTC-USDT y ETH-BTC, los nombres primero. Buscar dentro de una moneda de
  cotización se queda en ella. Los símbolos pueden guardarse para la búsqueda
  en todo.

## El límite de solicitudes

OKX limita cada clase de solicitud por separado: tantas en dos segundos — 20
para velas, 20 para operaciones, 40 para el libro. DataPlayer cuenta sus
propias solicitudes y se detiene en el 40 % de cada una, así que nunca pasa
del 80 % de dos segundos cualesquiera; una solicitud por encima espera a los
dos segundos siguientes en vez de fallar, así que una descarga larga tarda
unos segundos más. Si OKX rechaza la dirección de todos modos, esa clase de
solicitud espera dos segundos.
