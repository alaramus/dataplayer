# Action registry

Date: 2026-08-21
Status: agreed
Subproject: 5

## Goal

So far the application only reads. The action registry answers the question
"what can be done with this node" so that the answer comes from the server and
the interface is built from it without a single branch on the source type.

The first real actions are writes to personal storage: create a folder,
rename, delete, upload a file. This closes the known deviation "nothing is
written to the personal directory": until now it was filled only by
`seed_storage` on the server.

PostgreSQL gets no actions in this subproject. That is not a gap but a check:
a source without a registry must answer 501, not pretend.

## What we learned about the old application

An analysis of `webapi/view.py:70`, `core/supported_actions.py` (765 lines) and
`webapi/view_services/connector_actions.py` produced five facts, and each is
closed by a decision here.

**Dispatch is `getattr(connector, action)`.** The client sends the name of an
adapter method, and it is called: `performer = getattr(connector, action)`,
`await performer(**params)`, where `params` is the whole request body. Any
public method of the object can be called, not only one intended as an action.

**Declaration and call diverged.** The only protection is `if not
hasattr(connector, action)`. The 765-line `ACTIONS` dictionary, which lists for
each type what it can do, takes no part in the check at all: it decorates the
interface rather than restricting the call. A new method becomes callable
without being declared anywhere.

**The action name carries structure as a string.** `custom_form::BinanceSymbol`,
`custom_form::PostgresForm::postgresql.conf` — a form description baked into
the name and parsed by splitting on `::`.

**Actions are declared on the source type, not on the node kind.** The lists
are given as pairs `connectors` / `get_catalog`, almost always verbatim copies
of each other. That is why `upload` is offered on a file and `download` on a
folder: there is nothing to tell them apart.

**Parameters are typed nowhere.** `params = {**data, ...}` goes into the method
as `**kwargs`; what exactly an action accepts is known only from its body.

## Decisions

### R1. The declaration is the call site

An action is an object that holds together the name, the title, the parameters
model and `run`. The registry stores these objects; only what is in it can be
called. Declaration and call have nowhere to diverge, as `ACTIONS` and
`hasattr` did: they are one entry.

```python
class Action[P: BaseModel](ABC):
    name: ClassVar[str]
    title: ClassVar[str]
    applies_to: ClassVar[frozenset[NodeKind]]
    destructive: ClassVar[bool] = False
    params_model: type[P]

    async def perform(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionResult:
        return await self.run(node_id, self.params_model.model_validate(raw))

    @abstractmethod
    async def run(self, node_id: str | None, params: P) -> ActionResult: ...
```

An abstract class here rather than a protocol is deliberate. It does exactly
one thing — validates the parameters against the action's model before calling
`run` — and that makes dispatch typed under `--strict`: `Mapping[str, Any]`
faces outward, a concrete model arrives inside `run`. The rejection of
inheritance in decision D2b concerned drivers with business logic growing
along many axes; here twenty lines of validation are inherited, and they have
no axis of growth.

### R2. Actions are one more optional capability

```python
@runtime_checkable
class SupportsActions(Protocol):
    async def available(self, node_id: str | None) -> list[Action[Any]]: ...
    def action(self, name: str) -> Action[Any]: ...
```

Next to `SupportsCatalog` and `SupportsFetch`, by the same rule: the route
checks the capability and answers 501 if it is missing. PostgreSQL does not
implement the protocol.

`available` returns action objects, not names: the route gets the title and
the parameters schema from them as well, not from a second source of truth.

**Refined during implementation.** The protocol was meant to have a third
method — `run`, by which the adapter would perform an action by name. It turned
out to be a superfluous layer: since `action(name)` already returns the object
itself, the route calls it directly, and there is nowhere to resolve the name a
second time. Fewer methods means fewer places where a name can be resolved
differently.

### R3. Applicability is asked of the server for a specific node

`GET /connectors/{id}/actions?node_id=…`. The server decides what applies, and
checks it with the same function on execution — the rule lives in one place.

Rejected: handing out the lists statically in `GET /adapter-types` and matching
them to the node kind on the frontend. Then the applicability rule ends up both
in the client's filter and in the server's check, and that is exactly the case
ENGINEERING.md calls a defect.

Rejected: putting the list of actions into every catalog node. `CatalogNode`
describes what is, not what can be done; a listing of a thousand files would
grow by a thousand identical lists.

A per-node request was chosen also because applicability depends not only on
the node kind but on its state: the root of a connector is an ordinary folder,
but it cannot be deleted or renamed. The driver removes such actions from the
response itself.

### R4. The transport is declared by a protocol, not a field

For an upload the body is bytes, not JSON. An action that accepts a file
implements an additional protocol:

```python
class FilePayload(Protocol):
    filename: str | None
    async def read(self, size: int) -> bytes: ...


@runtime_checkable
class TakesFile(Protocol):
    async def perform_with_file(
        self, node_id: str | None, raw: Mapping[str, Any], payload: FilePayload
    ) -> ActionResult: ...
```

The `takes_file` field in the API response is **derived** by an `isinstance`
check, as `secret_field_names` is derived from `SecretStr`, not set by hand:
the declaration and the implementation cannot diverge.

`FilePayload` is its own protocol, not `fastapi.UploadFile`, which satisfies it
structurally. The driver should not know about the web framework, and a test
should not have to start it to pass ten bytes.

There are two endpoints because HTTP has two body shapes, and each refuses an
action of the other transport. The list of "what can be done here" stays one.

### R5. The server decides which part of the tree to reload

```python
class ActionResult(BaseModel):
    message: str
    reload_node_id: str | None   # whose branch to reload; None — the connector root
```

Each of the four actions changes the content of exactly one directory, and
which one is known to whoever performed the action. The client does not derive
it from the action name.

### R6. A name from a form is judged by the same rule as a path segment

`create_folder` takes `name`, `rename` takes `new_name`, an upload brings
`filename` inside multipart. All three are strings from the client, and all
three go through `is_plain_name` from `file/session.py` — the rule became
public along the way and stricter: a segment with a separator of either of the
two platforms is now rejected as well, — after which the result is resolved through `session.resolve`. No new path rules are introduced: the boundary stays
one, as decision D8 promises.

Separately about uploads: the filename from multipart is a client string too,
and `../evil` in it must be rejected the same way as in `node_id`.

### R7. Destructiveness is declared, confirmation is generic

`destructive: bool` in the action declaration. The dialog shows a confirmation
by this flag, not by a list of names like `ws_actions` in the old route.

The `recursive` and `overwrite` flags live in the parameters schema and default
to `false`: a non-empty folder and a taken name give a refusal until the user
explicitly says otherwise. The protection against data loss is on the server;
the client only draws the checkbox the schema already describes.

## File source actions

A new capability module `adapters/file/actions.py` next to `catalog.py` and
`fetch.py` (decision D2b): the session knows nothing about actions, the actions
know about the connection.

| Action | Applies to | Parameters | Refusal |
| --- | --- | --- | --- |
| `create_folder` | directory | `name` | name taken → 409 |
| `rename` | directory, file | `new_name` | name taken → 409; root → 422 |
| `delete` | directory, file | `recursive: bool = False` | non-empty folder without the flag → 409; root → 422 |
| `upload` | directory | `overwrite: bool = False` + file | name taken without the flag → 409; over the ceiling → 413 |

**An upload is streamed.** Chunks are read from the request and written through
`to_thread.run_sync` to a temporary file in the same directory, then
`os.replace` — a catalog reader never sees a half-written file under its real
name. The ceiling is the `MAX_UPLOAD_BYTES` setting; when it is exceeded the
temporary file is deleted and the response is 413. The size is counted as it is
read, not taken from the header: the client's header cannot be trusted.

**All I/O goes through `to_thread.run_sync`**, as in the catalog and reading.
ruff catches `open()` in `async def`; nobody catches `os.mkdir` and
`os.replace`.

## API

```
GET  /api/v1/connectors/{id}/actions?node_id=…      → list[ActionInfo]
POST /api/v1/connectors/{id}/actions/{action}       → ActionResult
POST /api/v1/connectors/{id}/actions/{action}/file  → ActionResult
```

```python
class ActionInfo(BaseModel):
    name: str
    title: str
    destructive: bool
    takes_file: bool
    params_schema: dict[str, Any]
```

`params_schema` is the JSON Schema of the parameters model, the same response
shape as `GET /adapter-types`, and the same `SchemaForm` draws it.

Response codes — one rule per cause:

| Code | Cause |
| --- | --- |
| 501 | the source does not implement `SupportsActions` |
| 404 | no connector; this source has no such action |
| 422 | the action does not apply to the node; path outside the root; parameters failed the schema |
| 409 | name taken; non-empty folder without `recursive` |
| 413 | upload ceiling exceeded |
| 415 | the action was called through the endpoint of the other transport |
| 502 | `AdapterError` from the source |

409, 422 and 413 come from one exception with a cause field, not from three
different ones: the mapping of cause to code lies in the route, in one table.

## Frontend

`SchemaForm/` moves from `features/connectors/` to `shared/`. This is its second
use — exactly the moment when generalising is justified rather than premature;
otherwise `catalog` would start importing `connectors`, and the link between
capabilities would go sideways.

The panel above the tree is built from the server's response: a button per
action, a dialog with the parameters form, a confirmation for `destructive`, a
file picker for `takes_file`. There is no branching on the source type
anywhere.

After success the `reload_node_id` branch is reloaded. vue-query invalidation
is not enough: QTree keeps children in the nodes themselves, so a
`reload(nodeId)` is needed that re-requests the children and replaces
`node.children`. This is an already known property of the screen, not a
discovery of this subproject.

## How it is checked

Backend:

- an undeclared driver method cannot be called through the API;
- an unknown action name → 404, any action on PostgreSQL → 501;
- parameters off the schema → 422 with a `loc` pointing at the field;
- the happy path of each of the four actions in a temporary directory;
- `..`, an absolute path, a segment with a drive letter and a symlink outward —
  both in `node_id` and **in the filename from multipart**;
- deleting and renaming the connector root → 422;
- a taken name → 409; a non-empty folder without `recursive` → 409; after the
  refusal the files are in place;
- exceeding `MAX_UPLOAD_BYTES` → 413, no temporary file left behind;
- a file action on the JSON endpoint and vice versa → 415;
- another user's connector → 404, and the error text has no absolute server
  path;
- `mypy --strict`, `ruff`, `lint-imports` are clean.

Frontend: a unit test of the pure mapper from the response to button
descriptions; a Playwright scenario — create a folder and see it in the tree,
upload a file and open it in the grid, rename, delete with confirmation.

## Not in this subproject

- downloading and streaming out — subproject 7;
- moving and copying between nodes and between connectors;
- quotas and accounting of used space;
- upload progress and resumption;
- actions on PostgreSQL;
- a log of performed actions;
- paging of catalog children and the connection pool — still subproject 4b.
