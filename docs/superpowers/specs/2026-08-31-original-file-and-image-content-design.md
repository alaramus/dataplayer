# Download actions and bounded image content

## Problem

D47 says how a catalog node may be viewed, and D48 says how a complete text
document may be edited. Neither operation describes downloading a selection.
Putting **Download original** in every viewer and on every catalog row makes
the browser decide that a node is a file, that only one node is involved and
that the source can return original bytes. Those are source rules, and they
break as soon as an object store, archive source or another adapter has a
different result.

Images expose a separate concern. A filename ending in `.png` is cheap to
classify while listing a directory, but it does not prove that the bytes are a
PNG. A compressed image can also be small on disk and enormous when decoded.
Viewing therefore needs verified format, dimensions and independent bounds;
downloading does not make the viewer responsible for the object.

## Download is an action transport

A source that can download catalog nodes declares an action named `download`
with the title **Download**, `acts_on="node"`, `requires="read"` and the node
kinds it accepts. The action implements `ProducesDownload`, beside the existing
JSON, file-upload and preview transports. `ActionInfo.downloads` is derived
from that callable protocol, so a client never switches on the action name or
adapter type.

The catalog's one Actions menu is the only place that starts it. It receives
the checked node ids once as an ordered, non-empty set. There is no download
button in a content/fetch panel and no per-row download icon. An adapter that
wants the same UI declares the same capability and owns the result semantics.

The file source applies these rules:

- one selected file returns its unchanged bytes and filename;
- more than one selected node returns `download.zip`;
- any selected directory makes the result an archive; one directory is named
  `<directory>.zip`;
- selected directories are recursive and empty directories are retained.

The archive is staged in a temporary file by a worker thread, not assembled in
application memory. It is limited to 10,000 entries and 2 GiB of uncompressed
file bytes, refuses symbolic links, preserves each selected node under its own
name and refuses ambiguous duplicate top-level names. The temporary file is
removed after streaming or interruption.

## Native browser boundary

The authenticated action POST validates the action, access and every selected
node, then returns a URL with a signed one-minute ticket. A normal browser
navigation follows it. Redemption re-checks that the user is active, still has
the action's required access, the connector is enabled, the action still
exists and every selected node still admits it. Only then does the source
prepare and stream `ActionDownload` with filename, media type and exact byte
length.

The ticket names a user, connector, action and opaque node ids. It never names
a server path. This two-request shape lets the browser stream to its download
destination; an authenticated XHR would first rebuild the response as a
JavaScript `Blob`.

## Image is a bounded content representation

The representation vocabulary gains `image`. The file catalog advertises it
for PNG and JPEG names because opening every file during a directory listing
would turn one list into thousands of reads. `read_content` verifies the bytes
and returns filename, verified MIME type, byte length, width, height and a
short-lived inline preview URL.

An image preview is accepted only when all of these hold:

- the file is at most 20 MB;
- decoded dimensions are positive and at most 40 million pixels together;
- Pillow identifies and verifies PNG or JPEG;
- the identified format agrees with the requested representation, regardless
  of the filename.

The verified bytes are the bounded bytes returned, avoiding a check-then-read
race. The preview response uses the decoder's media type, inline disposition,
`Cache-Control: private, no-store` and `X-Content-Type-Options: nosniff`.
Downloading the same node is still a separate source action.

## Rejected alternatives

- **Put download controls in viewers or rows.** That assigns source semantics
  to the screen and cannot express one operation over several selections.
- **Build ZIP in the browser.** Every object would first cross into JavaScript
  memory, and the client would have to understand directory traversal.
- **Put base64 in a JSON response.** It expands and duplicates an unbounded
  value instead of streaming it.
- **Store server paths in tickets.** Paths bypass the adapter's containment
  rule and are not source identities.
- **Infer image MIME in the browser.** A misleading suffix or corrupt file
  would be rendered under a type the source never verified.

## Known deviations and next slices

- Tickets are replayable until their one-minute expiry, although every
  redemption re-checks current access and applicability.
- Download streams have no byte-range contract. Audio and video need one.
- Archive creation is bounded by entry count and source bytes, but no user or
  process-wide staging quota exists yet.
- The preview is the bounded original PNG/JPEG, not a generated thumbnail.
- GIF, WebP, SVG, TIFF and icons have no viewer yet; they remain downloadable
  through the action.
- Archive *browsing* remains a later capability with its own decompression and
  containment rules; creating a download ZIP does not imply it.
