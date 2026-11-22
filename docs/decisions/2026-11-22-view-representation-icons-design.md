# Icons for view representations

Decision D445 adds an optional `icon` to `NodeRepresentation`. The generic
view head uses that Material Symbols name for the button that opens the
representation. When it is absent, the client keeps using the icon associated
with the representation kind. The title remains the tooltip and accessible
name in either case.

The kind describes how the data opens, not what its subject means. Two tables
may be different things: RabbitMQ messages are a log, while bindings are
connections between broker resources. Letting the source name the picture
distinguishes them without changing their table representation or adding
source-specific rendering to the client.

- Kafka messages use `receipt_long`.
- RabbitMQ stream messages use `receipt_long`.
- RabbitMQ queue and exchange bindings use `hub`.

Existing representations without an icon keep their current appearance and
opening behavior.
