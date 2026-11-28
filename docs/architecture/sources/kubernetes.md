# Kubernetes

What a Kubernetes source is: one type for every cluster, a managed one being a
way in and a card rather than a type (D463), how its API server is reached and
signed in to (D464), what its catalog shows, built from the cluster's own
discovery and tables (D465), what an object opens as and how a Secret's values
are kept back (D466), and who may do what and how a refusal is said (D467).
The contract every source type follows is in [contract.md](contract.md); the
SSH tunnel it may ride is D282 in [ssh.md](ssh.md), and the TLS helpers it
builds its context with are D446–D448 in [cloud-auth.md](cloud-auth.md). Read
this before changing the `kubernetes` adapter.

Decisions here: D463, D464, D465, D466, D467.

## D463. One type, with a managed cluster as a way in

GKE, EKS and AKS speak the same conformant API as any cluster; what differs
is how the API server is found and how a request is signed. So there is one
source type, `kubernetes`, and a managed cluster is a variant of the options
(`auth`, chosen first, as Docker's transport is) plus a card, never a type of
its own or a subclass. What only a managed cluster has is a report of the
Cluster section shown for that way in. Inheritance was rejected: a kubeconfig
pointing at GKE and a GKE account would be two types showing one cluster
differently, and each capability would be written against a base and checked
on every heir.

Spec: [2026-11-28-kubernetes-source-design.md](../../decisions/2026-11-28-kubernetes-source-design.md)

## D464. HTTPS with httpx, and a kubeconfig read as data

The API server is dialled with httpx; no Kubernetes client library — the
official one is synchronous and generated, and its loader runs whatever a
kubeconfig's `exec` names. `session.py` keeps one client per session, checks
`/version` once (a minor may read `27+`) and refuses a server below **1.27**.
TLS is always verified, through the context of D446 with the server's own
host as the name (D448), so an SSH tunnel's loopback port changes nothing.

The ways in (`options.py`, resolved by `endpoint.py` to an `Endpoint`):

- **kubeconfig** — a secret; `yaml.safe_load` once per session, and of the
  chosen context only `server`, `certificate-authority-data`,
  `tls-server-name`, `client-certificate-data`, `client-key-data` and `token`
  are read. Refused, each with its sentence: `exec` (with the cloud named for
  `gke-gcloud-auth-plugin`, `aws`, `aws-iam-authenticator`, `kubelogin`) and
  `auth-provider`, any field naming a file, `insecure-skip-tls-verify`, and
  `username`/`password`.
- **token** — server, CA (empty for public roots), a bearer token.
- **certificate** — server, CA, a client certificate and an unencrypted key.

Every variant takes an SSH tunnel and a namespace, declared last so the way in
is the form's first choice; a namespace holds the catalog to that one, for a
role that may not list namespaces.

The kubeconfig is the first secret whose line breaks matter: a `SecretStr`
with `layout(multiline=True)` reaches the form as `FieldSpec.multiline`, and
`SchemaFields` draws it as a box masked with `-webkit-text-security` until its
eye is pressed (`AppInput`'s `masked`). A one-line password field drops the
breaks, which a PEM survives (D446 rewraps it) and YAML does not.

*Checked*, k3s 1.33: the log subresource refuses `Accept: text/plain` with
406 and answers `*/*`. The shared `_NamedContext` (D448) spells out the
parameters of `wrap_socket` and `wrap_bio`, because anyio under httpx passes
`server_hostname` by position.

Spec: [2026-11-28-kubernetes-source-design.md](../../decisions/2026-11-28-kubernetes-source-design.md)

## D465. A catalog from discovery, tables from the cluster

`discovery.py` reads `/api/v1` and every group of `/apis` at its preferred
version, keeps the resources answering `list` and `get` that are not
subresources, and holds them five minutes. A group whose aggregated server is
down (`metrics.k8s.io` answers 503 until its pod is up, *checked*) hides its
kinds, not the cluster. Core kinds nobody lists any more (`endpoints`,
`componentstatuses`, `podtemplates`, `replicationcontrollers`) and both
`events` are left out; events have their report and pages.

The top level is **Cluster** (reports), **Namespaces** (**All namespaces**
first) and **Cluster resources**. A kind is shown in a section by a closed
map of well-known `group/resource`; everything else, custom resources
included, is **Other**, named with its group. Node ids are in `catalog.py`;
every part is matched against the API's name rules there and against
discovery before a request is built, and goes into a path as one
percent-encoded segment.

A kind's table is the server's own: the list asked with
`Accept: …;as=Table;v=v1;g=meta.k8s.io`, its column definitions typed by the
server and its "Age" replaced by **Created** from the row's metadata. Lists
are read in pages of 500 by `limit` and `continue` to 10,000 and narrowed in
memory (`listed.py`). A catalog node is one class for every kind,
`KubeObjectNode` (`k8s_object`), whose `summary` is the first two priority-0
columns after the name.

The Overview report counts pods by phase from metadata-only lists
(`as=PartialObjectMetadataList`): with a field selector the server leaves
`remainingItemCount` out (*checked*, 1.33). The identity is
`SelfSubjectReview`, `v1` then `v1beta1`.

Spec: [2026-11-28-kubernetes-source-design.md](../../decisions/2026-11-28-kubernetes-source-design.md)

## D466. What an object opens as, and a Secret kept back

An object opens as **Overview** (a view, D419, built by `card.py`), **As
YAML** (`text`) and **As JSON** (`tree`); its pages (D423) are **Events**
(`involvedObject` field selector), **Pods** for the kinds whose selector picks
them (a workload's `LabelSelector` or a Service's map, written as the API's
query reads it), and a pod's **Logs**, one page per container, newest first,
read as `tailLines` deep as the page reaches, at most 10,000 lines, 16 MB and
16 KB a line.

`managedFields` are left out of every representation. **A Secret's values
never leave the adapter in this slice**: its overview lists keys and sizes,
its YAML and JSON carry `<n bytes, hidden>` in place of each value of `data`
and `stringData`, and `kubectl.kubernetes.io/last-applied-configuration`,
which holds a copy, is removed. Known deviation from the spec: a value shown
on request, with `write`, is not here yet.

Spec: [2026-11-28-kubernetes-source-design.md](../../decisions/2026-11-28-kubernetes-source-design.md)

## D467. Who refused, said by what was asked

The way in failing — unreachable, a certificate not trusted, a handshake
refused, 401 — is said by the check and by every failed read. A 403 is said
as "The cluster does not let this connection {verb} {resource}" with the verb
and resource the adapter itself asked (`Forbidden`), never the `Status`
message, which names the identity and its groups. A 422 is said with the
field paths of `details.causes`; 409, 404 and 429 have sentences of their
own; anything else is logged by status alone. In this slice every action is
`read`; filtering a menu through access reviews comes with the first action.

Spec: [2026-11-28-kubernetes-source-design.md](../../decisions/2026-11-28-kubernetes-source-design.md)
