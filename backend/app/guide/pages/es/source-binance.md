# Binance

Los datos de mercado públicos de Binance: spot y futuros USDⓈ-M y COIN-M. Ves el
último día y las reglas de negociación de cada símbolo, y lees como filas las
velas, las operaciones y el libro de órdenes de un símbolo. No se cambia nada
en Binance y no hace falta ninguna clave. Cómo funcionan las conexiones en
general se explica en la página [Conexiones](connections.md).

## Qué puedes ver

- Spot y futuros USDⓈ-M y COIN-M, símbolos por activo de cotización
- Las últimas 24 horas de cada símbolo: precio, cambio, máximo, mínimo, volumen
- Las reglas de cada símbolo: paso de precio, paso de cantidad, orden mínima
- Las velas de un símbolo de cualquier intervalo, de un segundo a un mes
- Las operaciones de un símbolo, las más nuevas primero, por id o desde una hora
- El libro de órdenes de un símbolo, compras y ventas con sus acumulados
- Cualquiera de ellos descargado como archivo
- El estado de Binance, su reloj y cuánto del límite de solicitudes se usa
- El límite de solicitudes y las respuestas de Binance en un panel
- Símbolos encontrados por nombre o por activo
- Operaciones o velas de un símbolo llevadas por un pipeline, solo lo nuevo

## Qué puedes cambiar

- Nada: los datos de mercado solo se leen

## Conexión

La página **Conexión** de la ventana pide el **Punto de acceso**:

- **Binance** — los hosts principales, `api.binance.com`,
  `fapi.binance.com` y `dapi.binance.com`;
- **Binance, solo datos de mercado** — spot desde `data-api.binance.vision`,
  que solo sirve datos públicos y suele responder cuando el host principal
  está ocupado;
- **Red de pruebas** — la red de pruebas de Binance, con precios propios.

Binance rechaza algunos países. Si la comprobación dice que Binance no atiende
esta dirección, el servidor de DataPlayer está en uno de ellos y otro punto de
acceso no servirá.

## El catálogo

- Primero **Bolsa**: lo que Binance y esta conexión dicen de sí mismos.
- **Spot**, **Futuros USDⓈ-M** y **Futuros COIN-M**. Cada uno contiene **Tickers**, **Símbolos** y
  una carpeta por activo de cotización — **USDT**, **USDC**, **BTC** y el
  resto —, primero la que tiene más símbolos.
- Un activo de cotización contiene sus símbolos: solo los que se negocian
  ahora.
- Un símbolo contiene **Velas**, con una serie por intervalo,
  **Operaciones** y **Libro de órdenes**.

## Tablas

- **Tickers**: una fila por símbolo, el de más volumen de cotización primero.
  Cada columna se ordena y se filtra. Se actualiza cada diez segundos.
- **Símbolos**: una fila por símbolo con sus reglas. Los futuros añaden el
  tipo de contrato, su fecha de entrega y la fecha de alta.
- **Velas**: las más nuevas primero; ordenar por **open_time** empieza por
  las más antiguas, y un filtro sobre ella elige dónde empieza y termina la
  lectura. La vela aún abierta tiene `closed` en false.
- **Operaciones**: las operaciones agregadas de Binance, las más nuevas
  primero. Un filtro por **id** o **time** elige dónde empieza la lectura.
  Binance guarda unos dos años de operaciones spot y solo da las de futuros
  de los dos últimos días.
- **Libro de órdenes**: primero las mejores compras, luego las mejores
  ventas. Un filtro sobre **level** elige la profundidad, 100 niveles por
  defecto. Un filtro sobre **side** deja un solo lado.
- Una página de velas u operaciones llega como mucho a diez mil filas de
  profundidad. Para mirar más atrás, filtra por hora.
- **COIN-M** cuenta en contratos de 100 USD para BTC y 10 USD para el
  resto. Sus tickers y velas dan igualmente **volume** en el activo base y
  **quote_volume** en USD, como todo mercado; **Símbolos** añade
  **contract_size**. La **quantity** de una operación y del libro son
  contratos.
- Los precios y las cantidades son decimales exactos, tal como los escribe
  Binance.

## En un pipeline

Las **Operaciones** de un símbolo y cada serie de **Velas** pueden ser el
inicio de un enlace de pipeline que sigue leyendo: **Añadir los mensajes
nuevos a una tabla** o **a una tabla nueva**, o **Guardar lo último por
clave**. Cada ejecución lee solo lo que llegó desde la anterior, y **Seguir**
lo lleva en segundos.

- DataPlayer guarda dónde se detuvo cada enlace; Binance no.
- **La primera ejecución lee**: **Solo lo nuevo** empieza ahora; **Desde lo
  más antiguo disponible** empieza con la última hora de operaciones o el
  último día de velas.
- Una vela se lee cuando se ha cerrado.
- Una tabla que crea el enlace tiene una clave en el **id** de la operación o
  en el **open_time** de la vela, así que nada llega dos veces.
- Los tickers, los símbolos y el libro de órdenes son un momento, no una
  historia: un enlace los toma enteros en cada ejecución.

## Bolsa

- **Estado**: el punto de acceso, el estado propio de Binance — conocido solo
  en el punto de acceso principal — y si cada mercado responde.
- **Reloj**: la hora de cada mercado y cuánto va por delante del servidor de
  DataPlayer. Las horas que se envían a Binance son las del servidor, así que
  una diferencia grande las desplaza.
- **Límite de solicitudes**: lo que cada mercado permite por minuto, lo que
  esta dirección usó este minuto, dónde se detiene DataPlayer y si Binance
  retiene las solicitudes.
- **Mercados**: cuántos símbolos se negocian, en cuántos activos de
  cotización y cuándo se leyó la lista; se vuelve a leer al cabo de una hora.

## Paneles y búsqueda

- El panel **Conexión Binance** dibuja el peso usado cada minuto frente al
  umbral de DataPlayer, cuánto tarda Binance en responder y si cada mercado
  responde. Los precios no están en él: llévalos a una tabla con un pipeline y
  dibuja esa tabla.
- La búsqueda encuentra símbolos por nombre y por activo: `btc` encuentra
  BTCUSDT y ETHBTC, primero por nombre. Una búsqueda dentro de un activo de
  cotización se queda en él. Los símbolos se pueden guardar para la búsqueda
  en todo.

## El límite de solicitudes

Binance cuenta lo que cada dirección le pide por minuto y bloquea la dirección
que pide demasiado. DataPlayer lee la cuenta de cada respuesta y se detiene al
80 % del límite, diciendo cuántos segundos quedan del minuto. Si Binance
bloquea la dirección de todos modos, no se pide nada hasta que termine el
bloqueo.
