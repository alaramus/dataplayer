/**
 * How a source type is drawn in a list. A plain function, tested without
 * mounting anything. An unknown type gets a generic glyph rather than nothing:
 * the registry lives in the backend and gains entries without the frontend
 * being redeployed, so a missing entry here is a normal state.
 *
 * The drawings are files rather than glyphs of an icon font — a source type is
 * a product with a logo, and no font has those. Quasar loads one with the
 * `img:` prefix, served from `public/`.
 */
const ICONS: Record<string, string> = {
  postgres: "img:/icons/services/postgresql.svg",
  mysql: "img:/icons/services/mysql.svg",
  // A card of the `mysql` type rather than a type of its own (D264).
  mariadb: "img:/icons/services/mariadb.svg",
  cassandra: "img:/icons/services/cassandra.svg",
  // A card of the `cassandra` type (D340).
  scylladb: "img:/icons/services/scylladb.svg",
  sqlite: "img:/icons/services/sqlite.svg",
  clickhouse: "img:/icons/services/clickhouse.svg",
  mongodb: "img:/icons/services/mongodb.svg",
  zookeeper: "img:/icons/services/zookeeper.svg",
  kafka: "img:/icons/services/kafka.svg",
  rabbitmq: "img:/icons/services/rabbitmq.svg",
  binance: "img:/icons/services/binance.svg",
  redis: "img:/icons/services/redis.svg",
  file: "img:/icons/services/folder.svg",
  ssh: "img:/icons/services/ssh.svg",
}

export const UNKNOWN_ADAPTER_ICON = "cable"

export function adapterIcon(adapterType: string): string {
  return ICONS[adapterType] ?? UNKNOWN_ADAPTER_ICON
}

/**
 * A connection drawn as the product it was made for: the card it was picked
 * by, MariaDB rather than MySQL, and its type when it names none (D264).
 */
export function connectorIcon(connector: { adapter_type: string; face?: string | null }): string {
  return adapterIcon(connector.face ?? connector.adapter_type)
}

/**
 * The glyph beside a category in the catalog's sidebar.
 *
 * A glyph and not a logo: a category is a heading, not a product, so this is
 * an icon-font name rather than a file. What a category is *called* comes from
 * the server with the type — only the drawing is decided here, for the same
 * reason the logos above are.
 */
const CATEGORY_ICONS: Record<string, string> = {
  sql: "table_chart",
  document: "data_object",
  keyvalue: "key",
  stream: "view_stream",
  market: "candlestick_chart",
  files: "folder",
}

export const UNKNOWN_CATEGORY_ICON = "category"

export function categoryIcon(category: string): string {
  return CATEGORY_ICONS[category] ?? UNKNOWN_CATEGORY_ICON
}
