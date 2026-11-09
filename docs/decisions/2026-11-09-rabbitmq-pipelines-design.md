# RabbitMQ in pipelines

Decisions D335 and D336. The stage after the RabbitMQ source (D325–D334): a
stream and a queue read on by a pipeline's link, and an exchange, a queue or a
stream taking rows, so that Binance → RabbitMQ → databases is drawn as Binance
→ Kafka → databases is (D312–D315).

## Reading on (D335)

Both go through `SupportsReadingOn` (D312), so the two link kinds that read on
— Add new messages to a table, and to a new table — and following (D315) take
them without a line of their own.

**A stream** is read as a topic is: from a bookmark. RabbitMQ keeps a reader's
offset only for its stream protocol, which this source does not speak (D325),
so the bookmark is kept by this application in `reading_bookmark`, as
Binance's is (D319): the next offset. The line is the stream's end when the
step starts; `earliest` is the first offset the stream still keeps, `latest`
its end. A reader whose bookmark fell before the first kept offset counts the
gap as lost. A message is named by its offset, which a table the link makes
is keyed by (D313).

**A queue** has no position to keep: a message is taken and is gone once it is
acknowledged. So the link is the queue's consumer, as any worker is:

- The line is the number of ready messages when the step starts; what arrives
  later waits for the next run or the next poll of following.
- A block is taken without acknowledgement, on a channel the link holds; the
  block is written; then its keeping, `mark_read`, acknowledges it. A failure
  between the two leaves it unacknowledged, and the broker hands it out again
  when the channel closes: at least once. A channel nobody acknowledges on is
  closed after two minutes, so a run that died does not hold messages.
- Other consumers of the same queue share its messages with the link; a queue
  of the link's own, bound to an exchange, is how a person gives every link
  all of them. The first run's choice of earliest or latest means nothing for
  a queue and is not asked.
- A message has no position, so a table the link makes has no key.

The columns read from a queue are the message's own — redelivered, exchange,
routing key, timestamp, content type, headers, properties, body — with no
fields of the body, which would need a look at messages (D330) to find.

## Taking rows (D336)

A queue's and an exchange's page is their bindings, so the columns rows take
are not the page's. A node may say which columns rows moving out of it or into
it have (`SupportsMovingColumns`): the source end of a link reading on asks it
first, and so does the target end of any link writing rows.

Into an exchange, a queue or a stream, a row is a message. Its columns are the
message's own that a sender sets — the routing key for an exchange,
timestamp, content type, headers, properties and body — and, for every column
of the rows coming in, a column of the same name that becomes a field of a
JSON body. Pairing by name then pairs a whole row with the body's fields: a
Binance trade becomes `{"price": …, "qty": …}` without a line drawn by hand.
A field's text is read as JSON when it is a number, a boolean or an object,
and as text otherwise. A queue is published to through the default exchange by
its name; an exchange with the routing key a row carries, empty when none is
paired. A message an exchange routes to no queue is the exchange's business,
as it is for any publisher: rows are not published as mandatory.
