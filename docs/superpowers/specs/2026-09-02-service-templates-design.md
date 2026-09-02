# Approved service templates

## Goal

The first item of phase 4: a code registry of approved service templates and
generated credential fields, so that no image, command, environment key,
volume or host path comes from a client.

Nothing is started here. This slice decides *what would be started*, which is
the half that has to be right before anything runs it.

## What the old application did

`compose_file_creater.py` is 658 lines, and the shape of it is one dictionary
per concern keyed by the name of a service: `IMAGE_MAP`, `PORT_MAP`,
`WEB_PORT_MAP`, `DATA_PATHS`, `get_env_vars` with a twenty-entry `env_map`,
`get_commands` with another. Each of those had a client override in front of
it:

```python
def get_image_name(service_name, docker):
    return docker.get('image') or IMAGE_MAP.get(service_name, f"{service_name}:latest")
```

`docker` is `option_settings["docker"]`, which is `context.data["options"]["docker"]`
— the connector form's own payload. The same held for the command, the port,
the path inside the container and `host_config_path`, which was rendered into
a bind mount. The rendered Mako file was then passed to

```python
command_line = f'docker compose -p {SERVICE_NAME} -f {temp_compose_path} up -d {services_to_start}'
await run_subprocess_async(command_line)
```

so a client that could name an image could run any image on the machine, and
one that could name a host path could mount any directory into it.

Two more things came from the wrong side. The password was generated **in the
browser** — `generatePassword` in `dockerDemoPayload.ts` — and sent; and the
credentials the container was started with were read from `kwargs` while the
connector was saved from the form, so the two could differ.

## What replaces it

One value per approved service, in `templates.py`, holding both halves: what
runs, and what the connector to it becomes.

```python
POSTGRES = ServiceTemplate(
    key="postgres",
    image="postgres:18",
    container_port=5432,
    data_path="/var/lib/postgresql",
    credentials={USER: Fixed("dataplayer"), DATABASE: Fixed("dataplayer"), PASSWORD: Generated()},
    environment={"POSTGRES_USER": USER, "POSTGRES_PASSWORD": PASSWORD, "POSTGRES_DB": DATABASE},
    adapter_type="postgres",
    connector_options={"auth_method": Fixed("user_password"), "host": HOST, "port": PORT, ...},
)
```

Three things about that shape are deliberate.

**`Fixed` is a wrapper, not a bare string.** A template whose database is
literally called "database" would otherwise be indistinguishable from one
asking for the database slot.

**Slots are two types rather than one.** `CredentialSlot` — user, password,
database — is settled before the service starts; `PlacementSlot` — host,
port — is settled when it is placed. `environment` accepts only the first, so
a container that asked for a port nothing had assigned yet would not
type-check. This is the "closed set is a `Literal` union" rule from
ENGINEERING.md doing the work a runtime check would otherwise do badly.

**Both halves are one value.** The container and the connector are filled from
the same `credentials` mapping in the same plan, which is the defect from the
old application that cannot be reintroduced without deleting a field.

## The plan

`plan.py` is pure: the same inputs give the same answer and nothing talks to a
daemon. That is what makes "no arbitrary image, command, environment key,
volume or host path comes from the client" a thing a test holds rather than a
claim about a code path that runs only when Docker is listening.

`build_plan(template, service_id, owner_id, placement)` settles the
credentials once — this is the one moment a service's password comes into
existence — and describes the container: name, image, environment, command,
one named volume, the port inside, the port outside if it is published at all,
the network if there is one, and three labels.

Names are `dataplayer-svc-<template>-<first 12 of the service id>`, and the
volume is that plus `-data`. Labels are what code matches on when it later
looks for orphans; the name is for a person reading `docker ps`, and a name is
a thing that can be changed.

`connector_options(plan, endpoint)` fills the adapter's own options model, so
a connector made from a service is validated exactly as one somebody typed —
and its password reaches the encrypted blob through D4's schema split without
anything being told that it is a secret. A template naming a field that model
does not have is caught by a test over the whole registry rather than at the
moment somebody presses the button.

Neither `ServicePlan` nor `ContainerSpec` has a generated `repr`: the
environment holds the password, and one traceback with a spec in a local
variable would put it in a log for good. There is a test that it does not.

## What a client may know

`GET /api/v1/services/templates` lists the key, the title, the description,
the exact image, the container port, what the service becomes — in both the
adapter's name and its title, so no screen keeps a second name for a source
type — and which credentials the server generates.

The container itself is not published. It cannot be steered by a request, and
publishing it would invite the belief that it can.

## Decision

**D80. An approved service is written in code, and a client names one.** The
statement, its consequences and the known deviations are in
[managed services](../../architecture/services.md).

## What is not here

Starting anything. The next item models create, start, stop, restart and
delete as owned asynchronous jobs with durable state and realtime progress,
and a plan is what such a job carries out.
