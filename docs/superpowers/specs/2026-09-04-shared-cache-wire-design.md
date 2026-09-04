# The shared-cache wire format

## Problem

Process memory can retain typed Pydantic objects. Redis retains bytes shared by
different program versions and, unless deliberately protected, by anyone who
can read the service. Pickling those objects would make deployments dependent
on Python import paths and turn cache contents into executable input.

A Redis name must separate installations and users without dropping D31's
exact request identity. Invalidation is connector-wide and must still cross
every user who can read a shared connector.

## Names

One deployment chooses a bounded plain name. Values live below:

`dataplayer:<deployment>:cache:v1:user:<owner>:connector:<connector>:generation:<n>:<area>:<sha256(request)>`

The full request is authenticated with that name inside the encrypted value.
The digest only bounds the Redis key length; a collision cannot make one
request accept another's value. The invalidation generation is keyed by
deployment and connector, without a user, because a successful mutation must
invalidate the owner's and all grantees' cached reads together.

## Values

A value has a DataPlayer marker, a one-byte format version and JSON produced
and validated by the caller's declared Pydantic response type. Unknown versions
and invalid shapes are discarded as misses. There is no compatibility guess
and no pickle decoder.

The complete versioned value is encrypted with AES-GCM under a dedicated cache
key before it leaves the process. Its associated data is the full namespace and
the unhashed request. This protects both confidentiality and exact-key binding.

Everything is encrypted. Catalog names, query metadata and arbitrary fetched
cells may all be sensitive, and adapters do not have a truthful field-level
classification. TLS protects transport and Redis authentication limits access;
neither protects a persisted Redis dataset or backup from being read in plain
text.

## Rotation and compatibility

The cache key is independent of connector and query-content keys. Rotation
requires no data migration: values that cannot authenticate are misses and
expire under the source TTL. A wire-version change gets a new key namespace,
so old and new workers never decode each other's representations.

## Rejected alternatives

- Pickle can execute code and couples cache data to Python class locations.
- A deployment prefix without a user prefix risks cross-user reuse after a
  caller accidentally weakens an application key.
- Encrypting only rows labelled sensitive is impossible when values come from
  arbitrary external schemas.
- Reusing the connector-secret key couples unrelated rotation and disclosure
  domains.
