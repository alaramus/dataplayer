# Load tests

How many requests a second the backend answers before latency climbs. k6
sends a fixed rate for a fixed time, one step after another, and each step
prints one line; the run stops once the server falls behind (errors above
5 %, p95 above 5 s, or fewer than 90 % of the requested requests sent).

## What it needs

- [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) on the
  machine that sends the load (`winget install k6` on Windows).
- PowerShell 7 for `run.ps1`.
- A running backend, preferably the production build: development's
  `fastapi dev` reloads and debugs, which costs throughput.

  ```bash
  docker compose -f compose.yml -f compose.prod.yml -f compose.services.yml up -d --build
  ```

- An account on it. A scenario that reads rows needs a PostgreSQL connection
  with at least one table.

## Running

From the repository root:

```powershell
$env:DP_EMAIL = 'you@example.com'
$env:DP_PASSWORD = '...'
./loadtest/run.ps1 -Scenario me
./loadtest/run.ps1 -Scenario rows-fresh -Rates 25,50,100,150,200 -Duration 20s
```

| Parameter | Meaning | Default |
| --- | --- | --- |
| `-Scenario` | `login`, `me`, `connectors`, `catalog`, `rows`, `rows-fresh`, `mix` | `me` |
| `-Rates` | requests per second, one step each | `10,25,…,1600` |
| `-Duration` | length of a step | `30s` |
| `-BaseUrl` | backend address | `http://localhost:8000` |

`CONNECTOR_ID` and `NODE_ID` in the environment pick the connection and table;
otherwise the first enabled PostgreSQL connection and the first table found in
its catalog are used.

| Scenario | Request |
| --- | --- |
| `login` | `POST /login/access-token`: password hashing |
| `me` | `GET /users/me`: the floor of every authenticated request |
| `connectors` | `GET /connectors/` |
| `catalog` | the catalog level that holds the table |
| `rows` | one page of rows, from the server's read cache |
| `rows-fresh` | the same page with `refresh=true`, read from the source |
| `mix` | 40 % rows, 15 % fresh rows, 25 % catalog, 10 % connections, 10 % profile |

Each step's summary is written to `loadtest/results/`, which is not tracked.

## Reading the numbers

The backend is one process (D124), so its ceiling is one CPU core: watch
`docker stats` during a step. The knee is the last step where `achieved`
still equals `target` and p95 stays flat; after it requests queue and the
median jumps to seconds. k6 on the same machine competes for CPU, so the
numbers compare one build with another rather than promise a production
figure.

To see where the CPU goes, profile the running backend from a sidecar while a
step runs:

```powershell
docker run --rm --pid=container:dataplayer-backend-1 --cap-add SYS_PTRACE -v "${PWD}/loadtest/results:/out" python:3.14-slim sh -c "pip install -q py-spy && py-spy record -p 1 -d 25 -r 250 -f speedscope -o /out/profile.json"
```

Open the file at [speedscope.app](https://www.speedscope.app/).
