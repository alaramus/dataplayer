// One step of a load test: a fixed number of requests per second for a fixed
// time. run.ps1 calls this at rising rates and builds the table from the
// summaries, because k6's own summary of one ramping run averages every stage
// together and hides where latency starts to climb.
//
// Environment:
//   BASE_URL        backend address, default http://localhost:8000
//   DP_EMAIL        login
//   DP_PASSWORD     password; never written to a file
//   SCENARIO        login | me | connectors | catalog | rows | rows-fresh | mix
//   RATE            requests per second for this step
//   DURATION        e.g. 30s
//   CONNECTOR_ID    optional: the connection to read; otherwise the first
//                   enabled PostgreSQL one
//   NODE_ID         optional: the table to read; otherwise the first table
//                   found in its catalog
//   OUT             summary file to write

import http from 'k6/http';
import { check, fail } from 'k6';

const BASE = (__ENV.BASE_URL || 'http://localhost:8000') + '/api/v1';
const SCENARIO = __ENV.SCENARIO || 'me';
const RATE = Number(__ENV.RATE || 10);
const DURATION = __ENV.DURATION || '30s';

export const options = {
  scenarios: {
    step: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: Math.min(Math.max(RATE, 10), 500),
      maxVUs: 1000,
    },
  },
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  setupTimeout: '60s',
};

function login() {
  const res = http.post(
    `${BASE}/login/access-token`,
    { username: __ENV.DP_EMAIL, password: __ENV.DP_PASSWORD },
    { tags: { name: 'login' } },
  );
  if (res.status !== 200) fail(`login answered ${res.status}`);
  return res.json('access_token');
}

// Requests not answered in 30 s count as failures, not as slow successes.
function auth(token) {
  return {
    timeout: '30s',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  };
}

const READABLE = new Set(['table', 'view']);

// Walks the catalog breadth-first a few levels down, preferring `public`,
// until it meets something that has rows.
function findTable(token, connectorId) {
  let level = [null];
  for (let depth = 0; depth < 4; depth++) {
    const next = [];
    for (const nodeId of level) {
      const q = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : '';
      const res = http.get(`${BASE}/connectors/${connectorId}/catalog${q}`, auth(token));
      if (res.status !== 200) continue;
      const nodes = res.json();
      const table = nodes.find((n) => READABLE.has(n.kind));
      if (table) return { catalogNode: nodeId, table: table.id, tableName: table.name };
      const deeper = nodes.filter((n) => n.has_children);
      deeper.sort((a, b) => (b.name === 'public') - (a.name === 'public'));
      next.push(...deeper.slice(0, 3).map((n) => n.id));
    }
    level = next;
  }
  return null;
}

export function setup() {
  if (!__ENV.DP_EMAIL || !__ENV.DP_PASSWORD) fail('DP_EMAIL and DP_PASSWORD are required');
  const token = login();
  const res = http.get(`${BASE}/connectors/?limit=100`, auth(token));
  if (res.status !== 200) fail(`connectors answered ${res.status}`);
  const connectors = res.json('data') || [];

  let connector = __ENV.CONNECTOR_ID
    ? connectors.find((c) => c.id === __ENV.CONNECTOR_ID)
    : connectors.find((c) => c.enabled && c.adapter_type === 'postgres');
  const needsTable = ['catalog', 'rows', 'rows-fresh', 'mix'].includes(SCENARIO);
  if (needsTable && !connector) fail('no enabled PostgreSQL connection; set CONNECTOR_ID');

  let target = null;
  if (needsTable) {
    target = __ENV.NODE_ID ? { catalogNode: null, table: __ENV.NODE_ID } : findTable(token, connector.id);
    if (!target) fail(`no table found in ${connector.name}; set NODE_ID`);
    console.log(`reading ${connector.name}: ${target.tableName || target.table}`);
  }
  return {
    token,
    connectorId: connector ? connector.id : null,
    connectorName: connector ? connector.name : null,
    target,
  };
}

function catalogUrl(data) {
  const node = data.target.catalogNode;
  const q = node ? `?node_id=${encodeURIComponent(node)}` : '';
  return `${BASE}/connectors/${data.connectorId}/catalog${q}`;
}

function rowsBody(data) {
  // The same page every time: `rows` measures the server's read cache,
  // `rows-fresh` the same request with the cache skipped.
  return JSON.stringify({ node_id: data.target.table, limit: 100, offset: 0 });
}

const steps = {
  login: () => {
    const res = http.post(
      `${BASE}/login/access-token`,
      { username: __ENV.DP_EMAIL, password: __ENV.DP_PASSWORD },
      { tags: { name: 'login' } },
    );
    check(res, { ok: (r) => r.status === 200 });
  },
  me: (data) => {
    const res = http.get(`${BASE}/users/me`, Object.assign(auth(data.token), { tags: { name: 'me' } }));
    check(res, { ok: (r) => r.status === 200 });
  },
  connectors: (data) => {
    const res = http.get(`${BASE}/connectors/?limit=100`, Object.assign(auth(data.token), { tags: { name: 'connectors' } }));
    check(res, { ok: (r) => r.status === 200 });
  },
  catalog: (data) => {
    const res = http.get(catalogUrl(data), Object.assign(auth(data.token), { tags: { name: 'catalog' } }));
    check(res, { ok: (r) => r.status === 200 });
  },
  rows: (data) => {
    const res = http.post(
      `${BASE}/connectors/${data.connectorId}/fetch`,
      rowsBody(data),
      Object.assign(auth(data.token), { tags: { name: 'rows' } }),
    );
    check(res, { ok: (r) => r.status === 200 });
  },
  'rows-fresh': (data) => {
    const res = http.post(
      `${BASE}/connectors/${data.connectorId}/fetch?refresh=true`,
      rowsBody(data),
      Object.assign(auth(data.token), { tags: { name: 'rows-fresh' } }),
    );
    check(res, { ok: (r) => r.status === 200 });
  },
};

// Roughly what a person does: mostly reading rows and the catalog, now and
// then the list of connections and their own profile.
const MIX = [
  ['rows', 40],
  ['rows-fresh', 15],
  ['catalog', 25],
  ['connectors', 10],
  ['me', 10],
];

function pickMix() {
  let roll = Math.random() * 100;
  for (const [name, weight] of MIX) {
    roll -= weight;
    if (roll < 0) return name;
  }
  return MIX[0][0];
}

export default function (data) {
  const name = SCENARIO === 'mix' ? pickMix() : SCENARIO;
  const step = steps[name];
  if (!step) fail(`unknown SCENARIO ${SCENARIO}`);
  step(data);
}

export function handleSummary(summary) {
  const m = summary.metrics;
  const d = m.http_req_duration ? m.http_req_duration.values : {};
  const result = {
    scenario: SCENARIO,
    target_rps: RATE,
    achieved_rps: m.http_reqs ? m.http_reqs.values.rate : 0,
    requests: m.http_reqs ? m.http_reqs.values.count : 0,
    failed_pct: m.http_req_failed ? m.http_req_failed.values.rate * 100 : 0,
    dropped: m.dropped_iterations ? m.dropped_iterations.values.count : 0,
    max_vus: m.vus_max ? m.vus_max.values.max : 0,
    med_ms: d.med,
    p95_ms: d['p(95)'],
    p99_ms: d['p(99)'],
    max_ms: d.max,
  };
  const out = {};
  if (__ENV.OUT) out[__ENV.OUT] = JSON.stringify(result, null, 2);
  out.stdout = JSON.stringify(result) + '\n';
  return out;
}
