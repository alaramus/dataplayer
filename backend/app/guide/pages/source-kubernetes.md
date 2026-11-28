# Kubernetes

A Kubernetes cluster, reached through its API server: any cluster — your own,
k3s, kind, or one a cloud runs. You see its namespaces and every kind of
object it serves, custom ones included, as the cluster's own tables, what the
cluster says about each object, a pod's logs, and the cluster's reports. How
connections work in general is on the [Connections](connections.md) page.

## What you can see

- Namespaces, and every kind of object in each, grouped as kubectl users know
- Kinds that live outside namespaces: nodes, volumes, classes and more
- Custom resources, found the way built-in kinds are
- A kind's objects as the table `kubectl get` prints, sorted and filtered
- An object's overview: its state, metadata, conditions and what it holds
- An object as YAML or as a JSON tree
- The events about an object, and the pods a workload or a service picks
- A container's logs, newest first
- The cluster: version, nodes, pods by phase, events and its API resources

## What you can change

- Deployments, stateful sets and replica sets scaled
- Deployments, stateful sets and daemon sets restarted, as rollout restart
- Nodes cordoned, uncordoned and drained, the drain as a job
- Cron jobs suspended, resumed and run now
- Any object deleted, the cluster's own dry run first
- An object's YAML edited where it opens, and new objects from YAML

## Connecting

**Sign in with** chooses how DataPlayer signs in to the cluster:

- **A kubeconfig**: paste the file, or read it from disk with the button
  beside the field. The certificates and keys must be inside it, not named as
  files; `kubectl config view --minify --flatten` writes one like that.
  **Context** names the context to use; empty uses the file's current one.
- **A token**: the **API server**'s `https://` address, its **CA certificate**
  and a bearer **Token**, a service account's for instance.
- **A client certificate**: the API server, its CA, and a **Client
  certificate** and **Client key** the cluster accepts. The key must not be
  encrypted.

Leave **CA certificate** empty only for a server whose certificate a public
authority signed. **Namespace** stays empty to see every namespace you may
list; name one when your account may work only there.

Some kubeconfigs are refused, each with its reason:

- one that signs in by running a program — `gke-gcloud-auth-plugin`, `aws`,
  `kubelogin` and the like: DataPlayer runs nothing on its server;
- one that names files instead of holding their data;
- one that switches off checking the server's certificate;
- one that signs in with a user name and password, which Kubernetes removed.

**SSH tunnel** stays **Directly** unless the API server is reachable only
from inside another network. The cluster must run Kubernetes 1.27 or newer.

## The catalog

- **Cluster** holds the cluster's reports, below.
- **Namespaces** lists every namespace, with **All namespaces** first, which
  shows each kind across all of them with a **Namespace** column.
- Inside a namespace, its kinds are grouped: **Workloads**, **Network**,
  **Configuration**, **Storage** and **Other**. Other holds every kind the
  cluster serves that is not one of the well-known ones, custom resources
  among them, each named with its API group.
- **Cluster resources** holds the kinds that live outside namespaces, grouped
  the same way, with **Cluster** for nodes, namespaces and definitions.
- A kind opens as a table whose columns are the ones `kubectl get` prints
  for it, with **Created** in place of the age, so it sorts. Each object
  in the catalog shows its first columns beside its name, such as
  `1/1 · Running`. More than ten thousand of a kind are not listed.

## What an object opens as

- Click an object to open its overview: its kind, namespace, creation, owners
  and state, then what its kind is read for — a pod's node, addresses and
  containers with their images, states and restarts; a deployment's replicas
  wanted, ready and up to date; a service's type, addresses and ports; a
  node's versions and capacity; a volume claim's class and size — then its
  conditions, labels and annotations.
- The head of the overview opens the object **As YAML** or **As JSON** in a
  tab of its own. The fields Kubernetes keeps about who changed what are left
  out.
- Its pages open as tables in tabs of their own: **Events** about it; the
  **Pods** a deployment, stateful set, daemon set, replica set, job or service
  picks; and a pod's **Logs**, one page per container: time and text, newest
  first, up to ten thousand lines, each cut at 16 KB.
- **A secret's values are never shown.** Its overview lists its keys and their
  sizes, and its YAML and JSON put a size where each value is.

## The Cluster section

- **Overview**: the version, the server, the context, who the cluster takes
  you for, nodes ready, the platforms, and how many namespaces there are and
  pods in each phase.
- **Nodes**: each node's status, roles, versions, address, operating system,
  runtime, capacity, what can be allocated, and its taints.
- **Events**: what the cluster recorded lately, newest first.
- **API resources**: every kind the cluster serves, its group, version, scope
  and verbs.

## When something is refused

- The API server unreachable, its certificate not trusted, or your token or
  certificate not accepted stops the whole connection, and every screen says
  why.
- The cluster's own access rules may refuse one request. That is said as
  **The cluster does not let this connection** with what was asked, such as
  `list secrets`; the rest of the cluster stays readable.

## Changing things

The menu over an object, and the icons in the head of its overview, offer
only what the cluster lets your account do: an action its access rules would
refuse is left out. Scaling, restarting, cordoning and suspending need write
access to the connection; deleting, draining and new objects need structure
access.

- **Scale** asks for the number of replicas, the current one filled in, and
  says the change before it is made.
- **Restart** replaces a workload's pods one by one, as
  `kubectl rollout restart` does.
- **Cordon** and **Uncordon** stop and start new pods landing on a node.
  **Drain** cordons the node and evicts its pods one at a time as a job in
  **Activity**; DaemonSets' and static pods stay, a pod with `emptyDir` data
  waits for the box that says that data is lost, and a disruption budget is
  waited for up to the seconds you give.
- **Suspend**, **Resume** and **Run now** act on a cron job; Run now starts a
  job from its template, as `kubectl create job --from` does.
- **Delete** lets the cluster rehearse the deletion first and says what owns
  the object and will make it again; choose what happens to what it owns.
- **As YAML** opens an object for editing. Saving sends it back only if
  nobody changed it since you opened it; otherwise reload and edit again.
  Its kind, name and namespace stay as they were. A secret is not edited
  here.
- **New from YAML**, on a namespace or a kind, takes one or more objects. The
  cluster rehearses each first and the form shows what would be created or
  changed, or why one is refused; they are then applied in order.

## What Kubernetes does not have here yet

- A terminal inside a container, logs that keep up
- Metrics on a dashboard, search, and a database in the cluster opened
- Signing in to Google Kubernetes Engine with a Google Cloud account
- A secret's values, shown on request
