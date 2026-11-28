# A Kubernetes source

Decisions D463–D478. A source type that looks at and manages a Kubernetes
cluster through its API server: its namespaces and every kind of object the
cluster serves — built-in or added by a CustomResourceDefinition — what the
cluster says about each, a pod's logs, the cluster's events and reports, and
in later slices changing objects, a terminal inside a container, live logs,
metrics, search, and Google Kubernetes Engine signed in to with a Google Cloud
account. The whole plan is here; each slice is implemented and committed on
its own, and a fact a slice finds that changes a decision is recorded in the
architecture file (this spec stays as written).

Facts marked *checked* were tried on k3s v1.33.6 (`compose.override.yml`,
service `k3s`); facts marked *to check* are probed before the slice that
depends on them. Read [adding-a-source.md](../architecture/sources/adding-a-source.md)
first: like Docker's, this plan has its own slices, since a cluster has no
SQL, no rows to edit cell by cell and no columns to change, but the "every
slice" and "once per type" lists apply.

## One type, with GKE as a way in (D463)

GKE, EKS and AKS are Kubernetes: the API a client speaks to each is the same
conformant API, and what differs is how the API server is found and how a
request is signed. So there is **one source type, `kubernetes`**, and a
managed cluster is **a way of signing in** plus **a card** (D264), not a type
of its own and not a subclass:

- the way in is a variant of the options, chosen first, like Docker's
  transport (D418): a kubeconfig, a bearer token, a client certificate, or a
  cloud account (GKE in this plan; EKS and AKS are the same move with the AWS
  and Azure accounts D451 already keeps);
- what only a managed cluster has — GKE's node pools, release channel and
  Autopilot — is a report of the cluster section shown when the way in is that
  cloud's, not a second catalog.

The rejected alternative — a base `KubernetesAdapter` with `GkeAdapter`
inheriting from it — would put the way in into the class hierarchy, so a
kubeconfig that happens to point at GKE and a GKE account would be two types
showing the same cluster differently, and every capability would have to be
written against the base and checked on each heir. Polymorphism here is the
options union and the registry (ENGINEERING.md), not inheritance.

## How a cluster is reached and signed in to (D464)

The API server is dialled over HTTPS with httpx; **no Kubernetes client
library**. The official Python client is synchronous, generated, large, and
its configuration loader runs whatever a kubeconfig's `exec` names; the API is
REST and JSON, which this application already speaks everywhere. A websocket
(exec, attach, port-forward, slice 3) goes through `websockets`, already a
dependency of the market streams. YAML is read and written by PyYAML with
`safe_load` and `safe_dump` only.

The options are a discriminated union on `auth`:

- **kubeconfig** — the file's text, a secret (D4), pasted or read from a file
  (D446's file button), and the context to use (empty: its
  `current-context`). It is parsed on the server, once per session, by
  `yaml.safe_load`, and only these are read from the context's cluster and
  user: `server`, `certificate-authority-data`, `tls-server-name`,
  `client-certificate-data`, `client-key-data`, `token`. Refused with a
  sentence each:
  - **`exec` and `auth-provider`** — they run a program on this server. A
    kubeconfig whose `exec` is `gke-gcloud-auth-plugin` is told to use a Google
    Cloud account instead (D477); `aws` and `kubelogin` are told the same about
    AWS and Azure, which are not here yet;
  - **a path instead of data** (`certificate-authority`, `client-key`, …) —
    this server does not read its own files for anybody; the sentence says
    `kubectl config view --minify --flatten` writes the file with data in it;
  - **`insecure-skip-tls-verify`** — a cluster whose certificate is not
    checked can be anybody's; a missing CA is filled in the form instead;
  - **`username` and `password`** — removed from Kubernetes in 1.19.
  A kubeconfig is not shown back: what the form shows is the server and the
  context it read, so it can be checked without reading a secret.
- **token** — the server's address, its CA certificate (PEM; empty means the
  public roots, for a cluster whose certificate is a public one) and a bearer
  token (a service account's long-lived token, or any other), a secret.
- **certificate** — the server's address, its CA, a client certificate and its
  key (not encrypted), the key a secret; the TLS helpers of D446 build the
  context.
- **gke** — a Google Cloud account (D451) and the cluster (slice 5, D477).

Common to every variant:

- **an SSH tunnel** (D282) for a server on a private network, the
  certificate's name checked against the server's host and not the forwarded
  port (D448);
- **a namespace** — empty to see every namespace the identity may list; one
  name for an identity that may only work in it, since listing namespaces is
  often the first thing a restricted role cannot do (*checked*: a role without
  it gets 403 on `/api/v1/namespaces`).

**Every request asks the server's version first, once per session**, and the
floor is **1.27** (the oldest minor still in a cloud's extended support when
this was written), refused below with a sentence naming the server's version.
Nothing newer than 1.27 is used without asking the version first.

The connection string shown is `https://host:port` with the context or the
cluster's name; never a token or a key (D89).

## What the catalog shows (D465)

The catalog is built from **the cluster's own discovery**, not from a list
kept here: `/api` and `/apis` with each group's preferred version, and every
resource that answers `list` and `get` and is not a subresource. This shows
CustomResourceDefinitions' kinds with no code for them (*checked*: k3s's own
`helm.cattle.io` and `k3s.cattle.io` appear), and a kind a cluster does not
serve is not shown. Discovery is kept for the session for five minutes.

The top level:

- **Cluster** — reports read like tables (D55): **Overview** (version,
  platform, nodes ready of nodes, namespaces, pods by phase, the identity's
  name as `SelfSubjectReview` tells it, *to check* on 1.27), **Nodes** (name,
  status, roles, version, internal address, OS image, kernel, runtime, CPU and
  memory capacity and allocatable, taints, age), **Events** (the newest 500,
  warnings first when filtered), **API resources** (every kind discovery
  found, its group, version, scope and verbs);
- **Namespaces** — each namespace, its status and age; inside one, the kinds
  of objects in **groups**: Workloads (Pods, Deployments, StatefulSets,
  DaemonSets, ReplicaSets, Jobs, CronJobs), Network (Services, Ingresses,
  EndpointSlices, NetworkPolicies), Configuration (ConfigMaps, Secrets,
  ServiceAccounts, Roles, RoleBindings, ResourceQuotas, LimitRanges,
  HorizontalPodAutoscalers, PodDisruptionBudgets), Storage
  (PersistentVolumeClaims), and **Other**, by API group, for everything else
  discovery found, custom resources included;
- **Cluster resources** — the cluster-scoped kinds in the same groups: Nodes,
  Namespaces, PersistentVolumes, StorageClasses, ClusterRoles,
  ClusterRoleBindings, CustomResourceDefinitions, IngressClasses,
  PriorityClasses, and Other.

A kind's folder holds its objects; **a kind's table is the cluster's own
table**: the list asked with `Accept: application/json;as=Table;v=v1;g=meta.k8s.io`
answers the columns `kubectl get` prints, with a type and a priority, for
built-in and custom kinds alike (*checked*). Priority 0 columns are shown,
priority 1 are columns a person can show; the namespace is a column when the
level is "every namespace". Age is the object's creation time, not the
server's "5m", so it sorts.

**Lists are read whole, and bounded**: in pages of 500 by the API's own
`limit` and `continue` (*checked*), at most 10,000 of a kind, said when cut
(D2d); filters and sorting are the closed predicates of every source, applied
in memory (`listed.py`).

**A node is named by what the cluster names it by**: an object by its
namespace (empty for a cluster-scoped one), API group, resource and name, all
checked against discovery and against the API's name rules (a DNS subdomain
of at most 253 characters for a name, a DNS label for a namespace) before a
request is built; every part goes into the URL as a percent-encoded path
segment. An object deleted and made again with the same name is a new object
to the cluster (a new `uid`); to this catalog it is the same node, as it is to
`kubectl`.

## What an object opens as (D466)

Each object has more than one representation (D47), laid out as Docker's are
(D419–D424):

- **Overview** — a view (D419) of what it means: for every object its
  metadata (name, namespace, uid, created, labels, annotations, owners),
  conditions and a phase or state where it has them; for Pods, Deployments,
  StatefulSets, DaemonSets, ReplicaSets, Jobs, CronJobs, Services, Ingresses,
  Nodes, PersistentVolumeClaims and PersistentVolumes the fields that kind is
  read for (containers and their images, states and restarts; replicas wanted,
  ready and updated; ports and selectors; capacity and access modes; …);
- **YAML** — the object as the cluster holds it, `managedFields` left out,
  read only in this slice;
- **Events** — the events whose `involvedObject` is this object, newest first;
- a Pod's **Logs** — rows of time and text for one container (the first, or
  the one chosen), newest first, a page being the last 500 lines
  (`tailLines`, `timestamps=true`), a line cut at 16 KB; **Previous** reads
  the container's last terminated run;
- a Deployment's, StatefulSet's, DaemonSet's, ReplicaSet's, Job's and
  Service's **Pods** — the pods its selector picks, as rows that open them.

**A Secret's values are hidden until asked for** (D420's hidden value): its
overview lists the keys and sizes, and a value is decoded and shown when the
person asks for that one, which needs `write` on the connection, since `read`
on a shared connection must not hand out passwords. Its YAML shows `data` with
each value replaced by its size.

## Who may do what, and what the cluster refuses (D467)

Three things can say no, and a person is told which one did:

1. **This application, by the grant** (D33): `read` for D465–D466 (a Secret's
   value needs `write`); `write` for scaling, restarting, cordoning and
   suspending; `structure` for deleting, editing and creating objects and for
   draining a node; `own` for a terminal inside a container and port
   forwarding. As everywhere (D79), an action above the grant is not offered.
2. **The way in** — the server unreachable, its certificate not trusted, the
   token or certificate not accepted (401): said by the check and by every
   failed read.
3. **The cluster's RBAC** (403). Said as "The cluster does not let this
   connection {verb} {resource}", with the verb and resource the adapter
   itself asked for. The cluster's `message` is not passed on: it names the
   identity and the group, and the rest of a `Status` can carry admission
   webhooks' text. A `422` is said with the field paths of `details.causes`,
   which are the request's own; `409` is a changed object ("it changed since
   you read it; read it again"); `404` a node that is gone; `429` a
   disruption budget or the API's own throttling.

**What a menu offers is what the identity may do**: the actions of an object
are filtered through `SelfSubjectAccessReview` for the verb and resource each
needs, asked once a minute per namespace and kept for the session, so an
action the cluster would refuse is not offered; the route still answers the
cluster's refusal when it changed in the meantime.

## Slice 1 — read only

D463–D467 with the kubeconfig, token and certificate ways in, the user's
guide page in every locale (D183) with the Kubernetes card, and the test
stand:

- `k3s` in `compose.override.yml` under the `tools` profile: one privileged
  k3s server, its API on `127.0.0.1:6443`, an administrator's kubeconfig
  written to `deploy/k3s/kubeconfig` (git ignores it); a fixture applies a
  namespace with a deployment, a service, a config map, a secret and a
  custom resource before the tests.
- Backend tests that need it go through `tests/utils/services.py` and skip
  without it; everything else — kubeconfig parsing and its refusals, node ids,
  tables, refusals by status, version floor — is tested against
  `httpx.MockTransport` answers recorded from the stand.

## Changing objects (D468–D471, slice 2)

**D468. Scale, restart, cordon, suspend.** Scale a Deployment, StatefulSet or
ReplicaSet (the `scale` subresource, a count from 0 to 1,000); restart a
Deployment, StatefulSet or DaemonSet the way `kubectl rollout restart` does
(a patch of the pod template's `kubectl.kubernetes.io/restartedAt`
annotation); cordon and uncordon a node; suspend and resume a CronJob, and run
a CronJob now (a Job made from its template, named as kubectl names it). Each
answers what it would do (D46) and runs at once.

**D469. Deleting is reviewed.** Delete any object or a set of them (D68),
with the propagation chosen (background by default, foreground, orphan) and a
grace period for pods; the preview is the cluster's own dry run
(`dryRun=All`), which runs admission without changing anything, and names
what owns the object and what it owns. A namespace's deletion names what it
holds by kind.

**D470. Editing and creating are YAML, dry-run first.** An object's YAML
becomes editable; saving is a `PUT` with the `resourceVersion` read, so a
change made by somebody else in between is refused (409) rather than
overwritten, and the preview is the same `PUT` with `dryRun=All` and the
difference between what was read and what the cluster would keep. **New from
YAML** in a namespace or the cluster takes one or more documents, each
validated by a server-side apply dry run (`fieldManager=dataplayer`) before
any is applied; applying stops at the first refused document and says which
were applied.

**D471. Draining a node is a job** (D81): cordon, then evict every pod but
DaemonSets' and mirror pods through the `eviction` subresource, waiting on a
disruption budget's 429 up to a timeout chosen in the form; the job's progress
is pods evicted of pods to evict, and its outcome names what could not be
evicted.

## A terminal, live logs and port forwarding (D472–D474, slice 3)

**D472. A terminal inside a container is its owner's** (D148, D149, `own`):
`exec` over a websocket with the `v5.channel.k8s.io` subprotocol (falling
back to `v4`; *checked* on k3s 1.33), a program from a closed list —
`/bin/sh`, `/bin/bash`, `/bin/ash` — as argv, resized on the resize channel.
A container with no shell says so.

**D473. Live logs are a topic** (D18, D414's rules): one `follow=true` stream
per container while somebody watches, the last 1,000 lines kept by the
client, lines dropped with a count rather than a stalled stream.

**D474. A database in the cluster opens as a connection.** A Pod or a Service
whose image a source type declares (D417) offers **Open as connection**: a
draft of that type reaching it through a port forward this source keeps (the
`portforward` websocket with `v4.channel.k8s.io`, *checked* on k3s 1.33; the
connection names this one as its tunnel, host `<pod>.<namespace>.pod` or
`<service>.<namespace>.svc`) on a loopback port, credentials read from the pod's
environment by the target's conventions when they are literal values, never
from a Secret the connection may not read; `own` required.

## Metrics, search and export (D475–D476, slice 4)

**D475. Metrics from `metrics.k8s.io`** where the cluster serves it (k3s and
GKE do; *checked*: k3s answers 503 until its metrics server is up): nodes'
and pods' CPU and memory for dashboards (D125), at most 200 pods a poll, the
rest counted; a **Top** report of nodes and of pods in a namespace. A
cluster without it says so once in the report and polls nothing.

**D476. Search and export.** `EnumeratesNames` over namespaces and objects of
the kinds a person looks for most (Pods, Deployments, StatefulSets, Services,
ConfigMaps, Secrets' names, Nodes) within the bounds of D199;
`SupportsNodeSearch` over the same; a kind's table exported (D73) as it is
read.

## Google Kubernetes Engine (D477–D478, slice 5)

**D477. A GKE cluster is reached with a Google Cloud account.** The `gke` way
in names one of the owner's Google Cloud accounts (D451, a service account's
key or the server's own identity under D452) and a cluster: the form lists the
clusters the account may see through the Container API
(`projects/{project}/locations/-/clusters`), and stores its project, location
and name. Each session reads the cluster again — its endpoint (the public one,
the private one through a tunnel, or the DNS-based one), its CA and its
version — so an upgraded or re-addressed cluster needs no edit. A request is
signed with an OAuth 2 access token of scope `cloud-platform` that the account
issues (a new `SecretRequest`, `GoogleAccessToken`), asked again before it
expires, exactly as `gke-gcloud-auth-plugin` does without running it. The
account's IAM role decides what Kubernetes RBAC sees (`roles/container.developer`
for the test account).

**D478. What only GKE has is a report.** The Cluster section gains **GKE**:
location, release channel, control plane and node versions, Autopilot or
Standard, node pools (machine type, count or autoscaling bounds, Spot,
version, status), private and DNS endpoints, Workload Identity — read from the
same Container API answer. A kubeconfig made by `gcloud` is recognised by its
`gke-gcloud-auth-plugin` and the form offers to turn it into the `gke` way in
for the cluster it names.

## Not planned

- **EKS and AKS** — the same move as D477 with the AWS and Azure accounts;
  next, when wanted.
- **Helm releases** as their own nodes, watching the catalog live, editing a
  CRD's schema, `kubectl apply` of a folder or a kustomization.
- **A lab.** A cluster started here is a privileged container, which D86
  refuses; the test stand is a development tool, not a service template.
