# Managed services

A service this server starts on the machine it runs on, and the connector such
a service becomes. Read this before adding a template, changing what a service
is started with, or letting anything about a container come from a request.

Decisions here: D80.

## What exists today

A closed registry of approved templates, the plan one of them turns into, and
a route that lists what may be asked for. Nothing starts yet: what a plan is
executed by is the job model, which arrives next in
[the roadmap](../migration-roadmap.md).

```
backend/app/services/
├── templates.py   the closed set: what may run, and what it becomes
├── plan.py        one service fully decided — names, credentials, container
└── routes.py      GET /services/templates
```

```
GET /api/v1/services/templates
```

## D80. An approved service is written in code, and a client names one

The old application let the connector form describe the container. Ticking
"Deploy in Docker" sent `options.docker`, and `compose_file_creater.py` read
`image`, `commands`, `main_port`, `data_path`, `container_config_path` and
`host_config_path` straight out of it, rendered a Mako template with them and
ran the result through a `docker compose` command line built with an f-string.
A client that could name an image could run any image; one that could name a
host path could mount any directory into it.

- **A template is a value in `templates.py`**, and `SERVICE_TEMPLATES` is a
  tuple rather than a registry something can add to at runtime. There is
  nothing to implement for a service — unlike an adapter type, which registers
  a driver — so a template is data, and data a test can pin down.
- **A client sends a key and nothing else.** `template_for` is the one place a
  string becomes a template, and a key that names none does not resolve.
- **The image is pinned to a version.** `latest` is a statement about the day
  somebody presses the button rather than about what will run.
- **Every environment key is in the template**, and every value is either a
  constant written there or a slot the server settled. A key that is not
  declared is not passed.
- **What may stand where is a type, not a check.** A credential slot — user,
  password, database — belongs to one service and is settled before it starts;
  a placement slot — host, port — is settled when the service is put
  somewhere. The environment accepts only the first kind, so a container
  cannot ask for a port that nothing has assigned yet, and mypy is what says
  so.
- **The password is made here**, once per service, from `secrets` over letters
  and digits. The old frontend generated it in the browser. A template cannot
  choose its own alphabet, because a template that could would eventually
  choose a weak one.
- **Nothing names a path on the host.** A service gets one named volume,
  mounted where the image keeps its data; the data path is the image's
  business and is stated rather than guessed.
- **Names and labels are the server's.** A container is
  `dataplayer-svc-<template>-<service id>` and its volume is that plus `-data`,
  so what one installation made is visible in `docker ps`; the labels
  `dataplayer.service`, `dataplayer.template` and `dataplayer.owner` are what
  code matches on, because a name is for people to read and may be changed.
- **A plan holds the credentials it started the container with**, and the
  connector is filled from the same plan. The old application read the two out
  of different places, and could start a container with one password while
  saving a connector that held another.
- **The connector a service becomes goes through the adapter's own options
  model**, so it is validated exactly as one somebody typed, and the password
  lands in the encrypted blob by [D4](backend.md) without anything being told
  it is a secret.
- **Neither the plan nor the container spec has a readable `repr`.** One
  traceback with a spec in a local variable would put a password in a log for
  good.

Known deviations:

- **An image is pinned by tag, not by digest.** `postgres:18` is a moving
  target within its major version. A digest would be exact; keeping digests
  current is its own maintenance, and the tag is what the project's own
  `compose.yml` uses.
- **There is one template.** PostgreSQL is the pilot the roadmap names, and
  Redis arrives with its own item once the lifecycle is right.
- **Nothing runs yet.** The plan is pure, and what executes it — with durable
  state, progress and cancellation — is the next item of the phase.
- **A person cannot choose the database or the user.** Both are constants of
  the template. Letting them be typed would be a value from a client in an
  environment variable, which is a smaller thing than an image but still not
  this slice's to allow.

Spec: [Approved service templates](../superpowers/specs/2026-09-02-service-templates-design.md)
