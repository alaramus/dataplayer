"""What a node id of a MySQL source is made of (D229).

A database, or a database and a relation in it. MySQL accepts a dot in a
database's name, so the database part escapes its dots and backslashes and
the first dot left unescaped is the separator; a relation's name is
everything after it, dots and all.
"""


def database_id(database: str) -> str:
    return database.replace("\\", "\\\\").replace(".", "\\.")


def relation_id(database: str, relation: str) -> str:
    return f"{database_id(database)}.{relation}"


def parse(node_id: str) -> tuple[str, str | None]:
    """The database and the relation an id names; no relation for a database."""
    name: list[str] = []
    index = 0
    while index < len(node_id):
        character = node_id[index]
        if character == "\\" and index + 1 < len(node_id):
            name.append(node_id[index + 1])
            index += 2
            continue
        if character == ".":
            return "".join(name), node_id[index + 1 :]
        name.append(character)
        index += 1
    return "".join(name), None
