# Playing media, and reading a PDF

## Problem

D49 gave the platform a byte path: a signed ticket, a route that re-checks
everything, and verified bytes returned whole and inline. That is exactly right
for an image, which is small enough to hold and useless in pieces. It is wrong
for everything else that is not text.

A recording is not held: a forty-minute video is a gigabyte, and a player does
not want it from the beginning — it wants the last kilobytes first, because
that is where an MP4 keeps its index, and then the part it is about to play.
Without an answer to `Range` a browser will not seek at all, and some will not
play at all.

A PDF is not held either, and it brings a second problem the other formats do
not: it is an active-content format. Handing the bytes to an `<iframe>` means
handing them to the browser's own viewer, which understands annotations, forms
and a subset of JavaScript. That is a decision, not a default.

The old application had all three files and answered them as one: media was
base64-encoded into a table cell and a `.pdf` was whatever the browser did with
`application/pdf`. It also had a separate `/file_media/` route that did handle
`Range` correctly — the useful half of the evidence, along with the reason its
auth rode in a query parameter: a `<video>` element cannot send a header.

## A stream is a capability, and a range is the transport's business

`SupportsContentStream` is a source that can hand back part of a node's bytes:
`open_content_stream` answers with the verified media type, the filename, the
exact size, and a reader over an inclusive byte range. It is separate from
`SupportsContentPreview`, which returns bytes already held whole.

The route owns the HTTP: it parses one `Range`, answers `206` with
`Content-Range` or `200` with the whole body, answers `416` with
`Content-Range: bytes */size` for a range outside the file, and always says
`Accept-Ranges: bytes`. A multi-range request is answered with the whole body,
which is allowed and which no media element asks for. Nothing about ranges is
in the adapter, and nothing about files is in the route.

Authority is D49's ticket, because a `<video>`, an `<audio>` and a PDF fetch
cannot carry an Authorization header. The purpose in the ticket now names the
representation it was minted for, so a ticket for a sound file cannot be
redeemed for anything else.

## The bytes decide what they are

The catalog classifies by name because listing must not open every file. The
stream verifies before it serves a byte, and the media type it returns is the
one the container proves — never one guessed from the suffix, which is what
`mimetypes.guess_type` did in the old route.

Verification is a bounded read of the container's own header, with no
third-party decoder:

- **MP3** — an ID3v2 tag or a frame sync; `audio/mpeg`.
- **WAV** — `RIFF`…`WAVE` and the `fmt ` chunk, which also states channels,
  sample rate and, with the `data` chunk length, the exact duration.
- **FLAC** — `fLaC` and STREAMINFO, which states sample rate, channels and the
  total sample count, so the duration is exact.
- **Ogg** — `OggS`; `audio/ogg` or `video/ogg` by what the file is offered as.
- **ISO base media** — `ftyp`, then the top-level boxes are walked by their
  sizes, without reading what is inside them, until `moov`; `mvhd` states the
  duration and `tkhd` the picture size. `audio/mp4` or `video/mp4` by the
  representation, `video/quicktime` for `.mov`.
- **Matroska** — the EBML header, read to its `DocType`, which must be `webm`
  or `matroska`.
- **PDF** — `%PDF-` within the first kilobyte, as every reader looks for it,
  and the version beside it.

What is not proved is said plainly rather than guessed: a container states its
codecs in places a demuxer reads, so whether this browser can play this file is
the browser's answer, and the panel shows the browser's own failure when it
comes. Duration is absent rather than invented where the container hides it —
Matroska and Ogg say nothing here.

## A PDF is drawn by the application, not by the plugin

The document is rendered with `pdf.js`: pages to a canvas, with no annotation
layer, no forms and no scripting manager wired. (The plan named an
`isEvalSupported: false` option too; version 6 removed both the option and the
code path it disabled, so there is nothing to switch off.) What reaches the DOM
besides pixels is the text layer, which is text nodes positioned over the page
— it is what makes selection and the browser's own find work, and it carries no
markup. Nothing in the document can run.

This is the same decision D49 took about SVG, and the same one D50 took about
Markdown: what a document can execute is not the browser's business to decide
for us. It costs a lazily loaded renderer, which the document stack of D50
already established as the way to pay for a viewer.

Pages are rendered as they are scrolled to, so a thousand-page document costs
one page of canvas at a time, and `pdf.js` fetches the file through the same
ranged route.

## What is deliberately absent

- **No transcoding.** A format the browser cannot play stays downloadable and
  says so; the alternative is ffmpeg in the request path.
- **No posters, thumbnails or waveforms.** Each is a decoded frame or a whole
  scan of the audio, and neither is bounded by the header read this slice does.
- **No captions, chapters or playlists.** A subtitle file beside a video is a
  relation between two nodes, which is a contract of its own.
- **No AVI.** No browser plays it; claiming a viewer would be the promise the
  file source refuses to make elsewhere.
- **No PDF annotations, links or forms**, and no printing beyond what the
  browser does with the page.
- **No byte ceiling on a stream.** The transport is ranged and chunked, so the
  memory in play is one chunk; a ceiling would only forbid what already costs
  nothing to serve.

## Tests

Backend: the range parser against every form — none, whole, prefix, suffix,
past the end, reversed — and the route's 200, 206 and 416; a ticket minted for
one representation refused for another; each container verified and each
refused when the bytes do not match the name; the exact duration of a WAV and
of a FLAC; the duration and picture size of an MP4 whose `moov` sits at the
end; a stream that never reads more than the range asked for.

Frontend: the panel picks the element the representation names; a page of a PDF
is rendered and its page count shown; the browser's own playback failure is
reported rather than swallowed. End to end: a sound file plays, a video reports
its metadata, and a PDF shows its first page.
