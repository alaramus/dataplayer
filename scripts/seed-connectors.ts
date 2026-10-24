/**
 * Fill the connections panel with demo data: the same PostgreSQL under
 * several names, two file storages, Redis and a SQLite file.
 *
 * Usage, from the repository root:
 *
 *   bun scripts/seed-connectors.ts
 *   bun run seed:connectors
 *
 * Settings come from the environment, falling back to `.env`: the API needs
 * `FIRST_SUPERUSER` and `FIRST_SUPERUSER_PASSWORD`, PostgreSQL is `PG_URL` or
 * `POSTGRES_SERVER/PORT/DB/USER/PASSWORD`, and Redis uses
 * `DATA_CACHE_REDIS_URL`. Nothing is overwritten: a name that already exists
 * is skipped, so the script is safe to run again.
 */

import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dir, "..");
const API = process.env.API_BASE ?? "http://localhost:8000";

function readDotEnv(): Record<string, string> {
  const found: Record<string, string> = {};
  const file = path.join(ROOT, ".env");
  if (!fs.existsSync(file)) return found;
  for (const line of fs.readFileSync(file, "utf-8").split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (match) found[match[1]] = match[2].trim().replace(/^["']|["']$/g, "");
  }
  return found;
}

const env = { ...readDotEnv(), ...process.env };
const get = (name: string, fallback = ""): string => env[name] ?? fallback;
const required = (name: string): string => {
  const value = get(name);
  if (!value) throw new Error(`Set ${name} in the environment or in .env`);
  return value;
};

function postgresOptions() {
  const url = get("PG_URL");
  if (url) {
    const match = url.match(/^postgresql:\/\/([^:]+):([^@]+)@([^:]+):(\d+)\/(.+)$/);
    if (!match) throw new Error("PG_URL is not a postgresql://user:password@host:port/database URL");
    return {
      auth_method: "user_password",
      host: match[3],
      port: Number(match[4]),
      database: match[5],
      user: match[1],
      password: match[2],
    };
  }
  return {
    auth_method: "user_password",
    host: get("POSTGRES_SERVER", "db"),
    port: Number(get("POSTGRES_PORT", "5432")),
    database: get("POSTGRES_DB", "app"),
    user: get("POSTGRES_USER", "postgres"),
    password: get("POSTGRES_PASSWORD"),
  };
}

function redisCacheOptions() {
  const address = get("DATA_CACHE_REDIS_URL");
  if (!address) throw new Error("Set DATA_CACHE_REDIS_URL to connect the cache Redis");
  const url = new URL(address);
  if (url.protocol !== "redis:") {
    throw new Error("The Redis connector supports redis:// only; TLS rediss:// cache URLs are not supported yet");
  }
  if (!url.hostname) throw new Error("DATA_CACHE_REDIS_URL must include a Redis host");
  const pathDatabase = url.pathname.replace(/^\//, "");
  const database = pathDatabase ? Number(pathDatabase) : Number(url.searchParams.get("db") ?? 0);
  if (!Number.isInteger(database) || database < 0 || database > 15) {
    throw new Error("The Redis connector database must be between 0 and 15");
  }
  const password = decodeURIComponent(url.password);
  return {
    host: url.hostname,
    port: Number(url.port || 6379),
    database,
    ...(password ? { auth_method: "password", password } : { auth_method: "no_auth" }),
  };
}

async function api(pathname: string, token: string | null, init: RequestInit = {}) {
  const response = await fetch(`${API}${pathname}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  const text = await response.text();
  let body: unknown = text;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    /* keep the raw text */
  }
  return { status: response.status, body };
}

const TAB_COLORS = ["#246abc", "#2e7d32", "#6a1b9a", "#c62828", "#ef6c00", "#00838f", "#5d4037", "#455a64"];

async function main() {
  const login = await fetch(`${API}/api/v1/login/access-token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: required("FIRST_SUPERUSER"), password: required("FIRST_SUPERUSER_PASSWORD") }),
  });
  if (!login.ok) throw new Error(`Login failed with status ${login.status}`);
  const { access_token: token } = (await login.json()) as { access_token: string };

  const listed = await api("/api/v1/connectors/", token);
  const existing = new Set<string>(
    ((listed.body as { data?: Array<{ name: string }> }).data ?? []).map((connector) => connector.name),
  );

  const pgNames = [
    "pg-main", "pg-analytics", "pg-warehouse", "pg-logs", "pg-archive",
    "pg-staging", "pg-reporting", "pg-timescale", "pg-backup", "pg-lab",
  ];
  const wanted: Array<{ name: string; adapter_type: string; options: Record<string, unknown>; tab_color?: string }> = [
    ...pgNames.map((name, index) => ({
      name, adapter_type: "postgres", options: { ...postgresOptions() }, tab_color: TAB_COLORS[index % TAB_COLORS.length],
    })),
    { name: "files-personal", adapter_type: "file", options: {} },
    { name: "files-shared", adapter_type: "file", options: {} },
    { name: "redis-cache", adapter_type: "redis", options: redisCacheOptions() },
    // The lab file prestart writes into the superuser's storage (D261).
    { name: "sqlite-lab", adapter_type: "sqlite", options: { path: "lab.db" } },
  ];

  let created = 0;
  let skipped = 0;
  for (const item of wanted) {
    if (existing.has(item.name)) {
      skipped++;
      continue;
    }
    const response = await api("/api/v1/connectors/", token, { method: "POST", body: JSON.stringify(item) });
    if (response.status === 200 || response.status === 201) {
      created++;
      console.log(`created ${item.name}`);
    } else {
      console.log(`FAILED ${item.name}: ${response.status} ${JSON.stringify(response.body).slice(0, 300)}`);
    }
  }
  console.log(`done: created ${created}, skipped existing ${skipped}`);
}

main().catch((cause) => {
  console.error(cause instanceof Error ? cause.message : cause);
  process.exit(1);
});
