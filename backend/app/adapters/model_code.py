"""Writing the model a source published as code somebody else reads.

Three dialects, one input. `RelationModel` already describes a relation in
full (D22) — its columns, their types, its keys and its comments — so turning
that into a SQLAlchemy model, a Django model or a DBML document is a pure
function over what the source already said. No connection, no SQL, no second
description of a relation.

They read the published model rather than living in each driver as a copy
per source type, so a source that can describe a relation can be written out
in all three without knowing that any of them exists.

None of it claims to be a migration. What comes out is a starting point a
person edits: an ORM's opinion about a primary key, a default or a constraint
is not something this can guess, and pretending otherwise would produce code
that quietly disagrees with the database.
"""

import keyword
import re
from typing import Literal

from app.adapters.relation import (
    Column,
    ColumnType,
    ForeignKey,
    PrimaryKey,
    RelationModel,
    UniqueConstraint,
)
from app.core.translation import N_, say

CodeDialect = Literal["sqlalchemy", "django", "dbml"]

DIALECT_SUFFIX: dict[CodeDialect, str] = {
    "sqlalchemy": ".py",
    "django": ".py",
    "dbml": ".dbml",
}

DIALECT_TITLE: dict[CodeDialect, str] = {
    "sqlalchemy": N_("SQLAlchemy"),
    "django": N_("Django"),
    "dbml": N_("DBML (dbdiagram.io)"),
}

# How many relations one document may describe. A schema of five hundred
# tables is a document nobody reads and a request nobody should wait for.
MAX_RELATIONS = 200


def render(models: list[RelationModel], dialect: CodeDialect) -> str:
    """One document describing every relation given, in the chosen dialect."""
    if len(models) > MAX_RELATIONS:
        raise ValueError(say("At most {count} relations in one document", count=MAX_RELATIONS))
    # What is in the document, so a key can be written by the name of what it
    # points at rather than by an opaque id.
    known = {model.node_id: model for model in models}
    if dialect == "sqlalchemy":
        return _sqlalchemy(models, known)
    if dialect == "django":
        return _django(models, known)
    return _dbml(models, known)


# --- names -------------------------------------------------------------------


def class_name(name: str) -> str:
    """A relation's name as a class name, without pretending to be clever.

    `order_items` becomes `OrderItems` and not `OrderItem`: a singular is a
    guess about English, and a guess in generated code is a bug somebody has
    to find. Anything that cannot start an identifier is dropped, and a name
    that survives as nothing at all keeps a placeholder rather than producing
    a class called nothing.
    """
    parts = [part for part in re.split(r"[^0-9A-Za-z]+", name) if part]
    built = "".join(part[:1].upper() + part[1:] for part in parts)
    if not built or built[0].isdigit():
        built = f"Relation{built}"
    return built


def attribute_name(name: str) -> str:
    """A column's name as an attribute, or a safe stand-in for it."""
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", name)
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"field_{cleaned}"
    if keyword.iskeyword(cleaned):
        cleaned = f"{cleaned}_"
    return cleaned


def _quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _relation_of(model: RelationModel) -> str:
    """How a document refers to one relation: schema-qualified when it has one."""
    if model.schema_name is None:
        return model.name
    return f"{model.schema_name}.{model.name}"


def _target_name(
    reference: ForeignKey, known: dict[str, RelationModel]
) -> str:
    """What to call the relation a key points at.

    Its own published name when it is in the document, because a node id is
    opaque and reading one apart is exactly what D21 forbids. When it is not,
    the id is all there is — a generated file naming something outside itself
    is a line the reader fixes, and inventing a name would be worse.
    """
    target = known.get(reference.target_node_id)
    return reference.target_node_id if target is None else _relation_of(target)


def _primary_key(model: RelationModel) -> list[str]:
    for constraint in model.constraints:
        if isinstance(constraint, PrimaryKey):
            return list(constraint.columns)
    return []


def _foreign_keys(model: RelationModel) -> list[ForeignKey]:
    return [one for one in model.constraints if isinstance(one, ForeignKey)]


def _unique_single(model: RelationModel) -> set[str]:
    """Columns a one-column unique constraint stands on."""
    return {
        constraint.columns[0]
        for constraint in model.constraints
        if isinstance(constraint, UniqueConstraint) and len(constraint.columns) == 1
    }


# --- SQLAlchemy --------------------------------------------------------------

_SQLALCHEMY_TYPES: dict[str, str] = {
    "boolean": "Boolean",
    "datetime": "DateTime",
    "binary": "LargeBinary",
    "json": "JSON",
    "uuid": "Uuid",
    "enum": "String",
    "network": "String",
    "geometric": "String",
    "range": "String",
    "composite": "String",
    "other": "String",
}


def _sqlalchemy_type(type_: ColumnType) -> str:
    """The nearest portable SQLAlchemy type, and nothing dialect-specific.

    A dialect type would tie the file to one database, which is the opposite
    of what somebody generating an ORM model is usually after. Where the
    published type carries a length or a precision, it is passed on.
    """
    if type_.category == "array":
        inner = "String" if type_.element is None else _sqlalchemy_type(type_.element)
        return f"ARRAY({inner})"
    if type_.category == "string":
        return "Text" if type_.length is None else f"String({type_.length})"
    if type_.category == "number":
        return _sqlalchemy_number(type_)
    if type_.category == "datetime" and type_.sql.lower().startswith("interval"):
        return "Interval"
    return _SQLALCHEMY_TYPES.get(type_.category, "String")


def _sqlalchemy_number(type_: ColumnType) -> str:
    sql = type_.sql.lower()
    if type_.scale is not None and type_.precision is not None:
        return f"Numeric({type_.precision}, {type_.scale})"
    if "bigint" in sql or sql in {"int8", "bigserial"}:
        return "BigInteger"
    if "smallint" in sql or sql == "int2":
        return "SmallInteger"
    if "double" in sql or "real" in sql or sql in {"float4", "float8"}:
        return "Float"
    if "numeric" in sql or "decimal" in sql or "money" in sql:
        return "Numeric"
    return "Integer"


def _sqlalchemy_column(
    model: RelationModel, column: Column, known: dict[str, RelationModel]
) -> str:
    keys = set(_primary_key(model))
    parts = [_quoted(column.name), _sqlalchemy_type(column.type)]
    for reference in _foreign_keys(model):
        if column.name in reference.columns:
            at = reference.columns.index(column.name)
            target = reference.target_columns[at]
            named = f"{_target_name(reference, known)}.{target}"
            parts.append(f"ForeignKey({_quoted(named)})")
    if column.name in keys:
        parts.append("primary_key=True")
    if not column.nullable and column.name not in keys:
        parts.append("nullable=False")
    if column.name in _unique_single(model) and column.name not in keys:
        parts.append("unique=True")
    if column.comment:
        parts.append(f"comment={_quoted(column.comment)}")
    return f"    {attribute_name(column.name)} = Column({', '.join(parts)})"


def _sqlalchemy(
    models: list[RelationModel], known: dict[str, RelationModel]
) -> str:
    lines = [
        "# Written from what the source published about these relations.",
        "# A starting point, not a migration: review the types and the keys.",
        "",
        "from sqlalchemy import (",
        "    ARRAY,",
        "    JSON,",
        "    BigInteger,",
        "    Boolean,",
        "    Column,",
        "    DateTime,",
        "    Float,",
        "    ForeignKey,",
        "    Integer,",
        "    Interval,",
        "    LargeBinary,",
        "    Numeric,",
        "    SmallInteger,",
        "    String,",
        "    Text,",
        "    Uuid,",
        ")",
        "from sqlalchemy.orm import declarative_base",
        "",
        "Base = declarative_base()",
        "",
    ]
    for model in models:
        lines.append("")
        lines.append("")
        lines.append(f"class {class_name(model.name)}(Base):")
        if model.comment:
            lines.append(f'    """{model.comment}"""')
            lines.append("")
        lines.append(f"    __tablename__ = {_quoted(model.name)}")
        if model.schema_name is not None:
            lines.append(
                f"    __table_args__ = {{\"schema\": {_quoted(model.schema_name)}}}"
            )
        lines.append("")
        if not model.columns:
            lines.append("    pass")
            continue
        if not _primary_key(model):
            lines.append(
                "    # This relation publishes no primary key; SQLAlchemy needs one."
            )
        for column in model.columns:
            lines.append(_sqlalchemy_column(model, column, known))
    return "\n".join(lines) + "\n"


# --- Django ------------------------------------------------------------------

_DJANGO_TYPES: dict[str, str] = {
    "boolean": "BooleanField",
    "datetime": "DateTimeField",
    "binary": "BinaryField",
    "json": "JSONField",
    "uuid": "UUIDField",
    "network": "GenericIPAddressField",
    "enum": "CharField",
    "geometric": "TextField",
    "range": "TextField",
    "composite": "TextField",
    "array": "JSONField",
    "other": "TextField",
}


def _django_field(type_: ColumnType) -> tuple[str, list[str]]:
    """The field class and the arguments its type asks for."""
    if type_.category == "string":
        if type_.length is None:
            return "TextField", []
        return "CharField", [f"max_length={type_.length}"]
    if type_.category == "number":
        return _django_number(type_)
    if type_.category == "datetime":
        return _django_datetime(type_), []
    return _DJANGO_TYPES.get(type_.category, "TextField"), []


def _django_datetime(type_: ColumnType) -> str:
    """Which of Django's four date-ish fields this type is.

    Asked of the whole type name rather than its first letters: `timestamp
    with time zone` begins with neither `date` nor `time`, and `interval` is
    not a moment at all.
    """
    sql = type_.sql.lower()
    if sql.startswith("interval"):
        return "DurationField"
    if sql.startswith("timestamp") or "datetime" in sql:
        return "DateTimeField"
    if sql.startswith("time"):
        return "TimeField"
    if sql.startswith("date"):
        return "DateField"
    return "DateTimeField"


def _django_number(type_: ColumnType) -> tuple[str, list[str]]:
    sql = type_.sql.lower()
    if type_.scale is not None and type_.precision is not None:
        return (
            "DecimalField",
            [f"max_digits={type_.precision}", f"decimal_places={type_.scale}"],
        )
    if "bigint" in sql or sql in {"int8", "bigserial"}:
        return "BigIntegerField", []
    if "smallint" in sql or sql == "int2":
        return "SmallIntegerField", []
    if "double" in sql or "real" in sql or sql in {"float4", "float8"}:
        return "FloatField", []
    if "numeric" in sql or "decimal" in sql or "money" in sql:
        return "DecimalField", ["max_digits=38", "decimal_places=10"]
    return "IntegerField", []


def _django_field_name(model: RelationModel, column: Column) -> str:
    """What the attribute ends up called, which a key column changes."""
    for reference in _foreign_keys(model):
        if column.name in reference.columns and len(reference.columns) == 1:
            return _reference_name(column)
    return attribute_name(column.name)


def _reference_name(column: Column) -> str:
    name = attribute_name(column.name)
    return name[: -len("_id")] if name.endswith("_id") and len(name) > 3 else name


def _django_column(
    model: RelationModel, column: Column, known: dict[str, RelationModel]
) -> str:
    keys = set(_primary_key(model))
    for reference in _foreign_keys(model):
        if column.name in reference.columns and len(reference.columns) == 1:
            return _django_reference(column, reference, known)
    field, arguments = _django_field(column.type)
    if column.name in keys and len(keys) == 1:
        arguments.append("primary_key=True")
    if column.nullable:
        arguments.append("null=True")
        arguments.append("blank=True")
    if column.name in _unique_single(model) and column.name not in keys:
        arguments.append("unique=True")
    arguments.append(f"db_column={_quoted(column.name)}")
    if column.comment:
        arguments.append(f"help_text={_quoted(column.comment)}")
    return f"    {attribute_name(column.name)} = models.{field}({', '.join(arguments)})"


# What Django calls each referential action it supports.
_ON_DELETE: dict[str, str] = {
    "cascade": "models.CASCADE",
    "set_null": "models.SET_NULL",
    "set_default": "models.SET_DEFAULT",
    "restrict": "models.RESTRICT",
    "no_action": "models.DO_NOTHING",
}


def _django_reference(
    column: Column, reference: ForeignKey, known: dict[str, RelationModel]
) -> str:
    """A single-column foreign key as a ForeignKey field.

    The `_id` suffix goes, because Django adds it back to the column it
    writes; `db_column` keeps the real name so the model still points at the
    table that exists.
    """
    stripped = _reference_name(column)
    target = class_name(_target_name(reference, known).rsplit(".", 1)[-1])
    arguments = [
        _quoted(target),
        f"on_delete={_ON_DELETE.get(reference.on_delete, 'models.DO_NOTHING')}",
        f"db_column={_quoted(column.name)}",
    ]
    if column.nullable:
        arguments.extend(["null=True", "blank=True"])
    return f"    {stripped} = models.ForeignKey({', '.join(arguments)})"


def _django(models: list[RelationModel], known: dict[str, RelationModel]) -> str:
    lines = [
        "# Written from what the source published about these relations.",
        "# A starting point, not a migration: review the types and the keys.",
        "#",
        "# `managed = False` throughout, because these tables already exist and",
        "# Django did not make them.",
        "",
        "from django.db import models",
        "",
    ]
    for model in models:
        lines.append("")
        lines.append("")
        lines.append(f"class {class_name(model.name)}(models.Model):")
        if model.comment:
            lines.append(f'    """{model.comment}"""')
            lines.append("")
        keys = _primary_key(model)
        if len(keys) > 1:
            lines.append(
                "    # A composite primary key; Django has none, so the columns"
            )
            lines.append("    # below are ordinary fields and unique_together says so.")
        for column in model.columns:
            lines.append(_django_column(model, column, known))
        lines.append("")
        lines.append("    class Meta:")
        lines.append("        managed = False")
        lines.append(f"        db_table = {_quoted(_relation_of(model))}")
        if len(keys) > 1:
            by_name = {column.name: column for column in model.columns}
            named = ", ".join(
                _quoted(_django_field_name(model, by_name[key]))
                for key in keys
                if key in by_name
            )
            lines.append(f"        unique_together = (({named}),)")
        if model.comment:
            lines.append(f"        verbose_name = {_quoted(model.name)}")
    return "\n".join(lines) + "\n"


# --- DBML --------------------------------------------------------------------


def _dbml_name(name: str) -> str:
    """A DBML identifier, quoted when it is not a plain one."""
    if re.fullmatch(r"[A-Za-z_][0-9A-Za-z_]*", name):
        return name
    return '"' + name.replace('"', '\\"') + '"'


def _dbml_settings(model: RelationModel, column: Column) -> list[str]:
    keys = set(_primary_key(model))
    settings: list[str] = []
    if column.name in keys:
        settings.append("pk" if len(keys) == 1 else "not null")
    elif not column.nullable:
        settings.append("not null")
    if column.identity is not None:
        settings.append("increment")
    if column.name in _unique_single(model) and column.name not in keys:
        settings.append("unique")
    if column.default is not None and column.identity is None:
        settings.append(f"default: `{column.default}`")
    if column.comment:
        settings.append(f"note: {_quoted(column.comment)}")
    return settings


def _dbml_relation(model: RelationModel) -> str:
    """A relation in DBML: the schema and the name, each quoted if it must be.

    Never the pair as one string: the dot between them is DBML's own schema
    separator, and quoting across it makes a table whose name contains a dot.
    """
    if model.schema_name is None:
        return _dbml_name(model.name)
    return f"{_dbml_name(model.schema_name)}.{_dbml_name(model.name)}"


def _dbml(models: list[RelationModel], known: dict[str, RelationModel]) -> str:
    """The whole selection as one dbdiagram.io document.

    References are written as their own statements rather than inline, because
    a composite key needs the bracketed form and one shape for both is one
    shape to read.
    """
    lines = [
        "// Written from what the source published about these relations.",
        "// Paste into https://dbdiagram.io to draw it.",
        "",
    ]
    for model in models:
        lines.append(f"Table {_dbml_relation(model)} {{")
        for column in model.columns:
            settings = _dbml_settings(model, column)
            written = f" [{', '.join(settings)}]" if settings else ""
            lines.append(
                f"  {_dbml_name(column.name)} {_dbml_name(column.type.sql)}{written}"
            )
        keys = _primary_key(model)
        if len(keys) > 1 or model.comment:
            lines.append("")
            if model.comment:
                lines.append("  Note: " + _quoted(model.comment))
            if len(keys) > 1:
                lines.append("  indexes {")
                lines.append(f"    ({', '.join(_dbml_name(key) for key in keys)}) [pk]")
                lines.append("  }")
        lines.append("}")
        lines.append("")
    for model in models:
        for reference in _foreign_keys(model):
            # A key pointing outside the selection would draw a table that is
            # not in the document, and dbdiagram refuses the file whole.
            if reference.target_node_id not in known:
                continue
            source = ", ".join(_dbml_name(one) for one in reference.columns)
            target = ", ".join(_dbml_name(one) for one in reference.target_columns)
            here = _dbml_relation(model)
            there = _dbml_relation(known[reference.target_node_id])
            lines.append(f"Ref: {here}.({source}) > {there}.({target})")
    return "\n".join(lines).rstrip("\n") + "\n"
