/**
 * Fill the connections panel with demo data: the same PostgreSQL under
 * several names, two file storages, two Redis databases and two SSH servers.
 *
 * Usage, from the repository root:
 *
 *   bun scripts/seed-connectors.ts
 *   bun run seed:connectors
 *
 * Settings come from the environment, falling back to `.env` and then to the
 * development defaults the E2E scenarios use: the API needs
 * `FIRST_SUPERUSER` and `FIRST_SUPERUSER_PASSWORD`, PostgreSQL is
 * `PG_URL` or `POSTGRES_SERVER/PORT/DB/USER/PASSWORD` as the backend
 * container sees it. Nothing is overwritten: a name that already exists is
 * skipped, so the script is safe to run again.
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

  // Pin the SSH server key once, the way the connection form does (D145).
  const keyReport = await api("/api/v1/connectors/server-key", token, {
    method: "POST",
    body: JSON.stringify({ adapter_type: "ssh", options: { host: "sshd", port: 2222 }, fetch: true }),
  });
  const presented = (keyReport.body as { presented?: { public_key?: string } | null })?.presented;
  if (keyReport.status !== 200 || !presented?.public_key) {
    throw new Error(`Could not fetch the SSH server key: ${keyReport.status} ${JSON.stringify(keyReport.body)}`);
  }
  const sshPassword = { auth_method: "password", host: "sshd", port: 2222, username: "dataplayer", password: "dataplayer", host_key: presented.public_key };

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
    {
      name: "redis-main", adapter_type: "redis",
      options: { auth_method: "no_auth", host: get("REDIS_HOST", "redis"), port: Number(get("REDIS_PORT", "6379")), database: 0 },
    },
    {
      name: "redis-queue", adapter_type: "redis",
      options: { auth_method: "no_auth", host: get("REDIS_HOST", "redis"), port: Number(get("REDIS_PORT", "6379")), database: 1 },
    },
    { name: "ssh-dev", adapter_type: "ssh", options: { ...sshPassword } },
    { name: "ssh-files", adapter_type: "ssh", options: { ...sshPassword, path: "/" } },
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
