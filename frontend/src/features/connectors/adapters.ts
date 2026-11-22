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
  duckdb: "img:/icons/services/duckdb.svg",
  clickhouse: "img:/icons/services/clickhouse.svg",
  mongodb: "img:/icons/services/mongodb.svg",
  zookeeper: "img:/icons/services/zookeeper.svg",
  kafka: "img:/icons/services/kafka.svg",
  rabbitmq: "img:/icons/services/rabbitmq.svg",
  binance: "img:/icons/services/binance.svg",
  bybit: "img:/icons/services/bybit.svg",
  okx: "img:/icons/services/okx.svg",
  redis: "img:/icons/services/redis.svg",
  file: "img:/icons/services/folder.svg",
  ssh: "img:/icons/services/ssh.svg",
  ftp: "img:/icons/services/ftp.svg",
  docker: "img:/icons/services/docker.svg",
  // A card of the `docker` type (D405).
  podman: "img:/icons/services/podman.svg",
  mail: "img:/icons/services/mail.svg",
  // A card of the `mail` type (D373).
  gmail: "img:/icons/services/gmail.svg",
  // Cards of `postgres`, `mysql`, `redis` and `kafka` (D377). A hosted
  // server's card wears its cloud's logo, whichever type it is of.
  timescaledb: "img:/icons/services/timescale.svg",
  citus: "img:/icons/services/citus.svg",
  paradedb: "img:/icons/services/paradedb.svg",
  supabase: "img:/icons/services/supabase.svg",
  neon: "img:/icons/services/neon.svg",
  "aws-rds-postgres": "img:/icons/services/aws.svg",
  "aws-rds-mysql": "img:/icons/services/aws.svg",
  "azure-postgres": "img:/icons/services/azure.svg",
  "azure-mysql": "img:/icons/services/azure.svg",
  "cloudsql-postgres": "img:/icons/services/googlecloud.svg",
  "cloudsql-mysql": "img:/icons/services/googlecloud.svg",
  percona: "img:/icons/services/percona.svg",
  valkey: "img:/icons/services/valkey.svg",
  keydb: "img:/icons/services/keydb.svg",
  redpanda: "img:/icons/services/redpanda.svg",
  // Cards of `redis` and `mysql` with a list of what they lack (D378).
  dragonfly: "img:/icons/services/dragonfly.svg",
  tidb: "img:/icons/services/tidb.svg",
  // The `s3` type and its cards (D382). Amazon S3 wears its cloud's logo.
  s3: "img:/icons/services/aws.svg",
  minio: "img:/icons/services/minio.svg",
  rustfs: "img:/icons/services/rustfs.svg",
  "cloudflare-r2": "img:/icons/services/cloudflare.svg",
  "backblaze-b2": "img:/icons/services/backblaze.svg",
  wasabi: "img:/icons/services/wasabi.svg",
  "digitalocean-spaces": "img:/icons/services/digitalocean.svg",
  gcs: "img:/icons/services/googlecloud.svg",
  "yandex-object-storage": "img:/icons/services/yandexcloud.svg",
  "vk-cloud": "img:/icons/services/vk.svg",
  selectel: "img:/icons/services/selectel.svg",
  hetzner: "img:/icons/services/hetzner.svg",
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
  mail: "mail",
  containers: "deployed_code",
}

export const UNKNOWN_CATEGORY_ICON = "category"

export function categoryIcon(category: string): string {
  return CATEGORY_ICONS[category] ?? UNKNOWN_CATEGORY_ICON
}
