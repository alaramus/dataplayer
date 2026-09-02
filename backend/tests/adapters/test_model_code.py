"""Writing a published model out as code somebody else reads.

Pure: the input is a `RelationModel`, which is what every source that can
describe a relation already produces, so none of this needs a database.
"""

import pytest

from app.adapters.model_code import (
    DIALECT_SUFFIX,
    attribute_name,
    class_name,
    render,
)
from app.adapters.relation import (
    Column,
    ColumnType,
    ForeignKey,
    PrimaryKey,
    RelationModel,
    UniqueConstraint,
)


def column(
    name: str,
    sql: str,
    category: str,
    *,
    nullable: bool = True,
    length: int | None = None,
    precision: int | None = None,
    scale: int | None = None,
    comment: str | None = None,
    identity: str | None = None,
    default: str | None = None,
    position: int = 1,
) -> Column:
    return Column(
        position=position,
        name=name,
        type=ColumnType(
            sql=sql,
            category=category,  # type: ignore[arg-type]
            length=length,
            precision=precision,
            scale=scale,
        ),
        nullable=nullable,
        comment=comment,
        identity=identity,  # type: ignore[arg-type]
        default=default,
    )


def orders() -> RelationModel:
    return RelationModel(
        node_id="shop.orders",
        schema_name="shop",
        name="orders",
        kind="table",
        comment="What people bought",
        columns=[
            column("id", "bigint", "number", nullable=False, identity="by_default"),
            column("customer_id", "integer", "number", nullable=False, position=2),
            column("code", "character varying(30)", "string", length=30, position=3),
            column(
                "total",
                "numeric(10,2)",
                "number",
                precision=10,
                scale=2,
                position=4,
                comment="In euros",
            ),
            column("placed_at", "timestamp with time zone", "datetime", position=5),
            column("paid", "boolean", "boolean", position=6),
        ],
        constraints=[
            PrimaryKey(name="orders_pkey", columns=["id"]),
            UniqueConstraint(name="orders_code_key", columns=["code"]),
            ForeignKey(
                name="orders_customer_fkey",
                columns=["customer_id"],
                target_node_id="shop.customers",
                target_columns=["id"],
                on_delete="cascade",
            ),
        ],
    )


def customers() -> RelationModel:
    return RelationModel(
        node_id="shop.customers",
        schema_name="shop",
        name="customers",
        kind="table",
        columns=[column("id", "integer", "number", nullable=False)],
        constraints=[PrimaryKey(name="customers_pkey", columns=["id"])],
    )


# --- names -------------------------------------------------------------------


def test_a_relation_becomes_a_class_without_guessing_at_english() -> None:
    # Not `OrderItem`: a singular is a guess, and a guess in generated code is
    # a bug somebody has to find.
    assert class_name("order_items") == "OrderItems"
    assert class_name("orders") == "Orders"
    assert class_name("2024_archive") == "Relation2024Archive"
    assert class_name("weird name!") == "WeirdName"


def test_a_column_becomes_an_attribute_that_python_accepts() -> None:
    assert attribute_name("customer_id") == "customer_id"
    assert attribute_name("class") == "class_"
    assert attribute_name("2nd") == "field_2nd"
    assert attribute_name("with space") == "with_space"


# --- SQLAlchemy --------------------------------------------------------------


def test_sqlalchemy_writes_the_table_its_keys_and_its_types() -> None:
    text = render([orders()], "sqlalchemy")

    assert "class Orders(Base):" in text
    assert '__tablename__ = "orders"' in text
    assert '__table_args__ = {"schema": "shop"}' in text
    assert "id = Column(\"id\", BigInteger, primary_key=True)" in text
    assert 'ForeignKey("shop.customers.id")' in text
    assert "String(30)" in text
    assert "Numeric(10, 2)" in text
    assert "DateTime" in text
    assert 'unique=True' in text
    assert 'comment="In euros"' in text


def test_sqlalchemy_says_so_when_a_relation_publishes_no_key() -> None:
    """It needs one, and a generated file that omits it fails at import."""
    model = orders().model_copy(update={"constraints": []})

    text = render([model], "sqlalchemy")

    assert "publishes no primary key" in text


# --- Django ------------------------------------------------------------------


def test_django_writes_unmanaged_models_against_the_real_columns() -> None:
    text = render([orders()], "django")

    assert "class Orders(models.Model):" in text
    assert "managed = False" in text
    assert 'db_table = "shop.orders"' in text
    assert "models.CharField(max_length=30" in text
    assert "models.DecimalField(max_digits=10, decimal_places=2" in text
    assert 'db_column="total"' in text


def test_django_turns_a_single_key_into_a_reference_without_the_id_suffix() -> None:
    text = render([orders()], "django")

    assert (
        'customer = models.ForeignKey("Customers", on_delete=models.CASCADE, '
        'db_column="customer_id")' in text
    )


def test_django_reads_the_whole_type_name_before_calling_it_a_time() -> None:
    """`timestamp with time zone` starts with "time" and is not one."""
    model = customers().model_copy(
        update={
            "columns": [
                column("at", "timestamp with time zone", "datetime"),
                column("on", "date", "datetime", position=2),
                column("clock", "time without time zone", "datetime", position=3),
                column("lag", "interval", "datetime", position=4),
            ]
        }
    )

    text = render([model], "django")

    assert "at = models.DateTimeField(" in text
    assert "on = models.DateField(" in text
    assert "clock = models.TimeField(" in text
    # A span, not a moment.
    assert "lag = models.DurationField(" in text


def test_sqlalchemy_calls_an_interval_an_interval() -> None:
    model = customers().model_copy(
        update={"columns": [column("lag", "interval", "datetime")]}
    )

    assert "Column(\"lag\", Interval)" in render([model], "sqlalchemy")


def test_django_names_the_fields_it_actually_wrote_in_unique_together() -> None:
    """A key column that became a reference is called by the reference's name."""
    model = RelationModel(
        node_id="shop.order_tags",
        schema_name="shop",
        name="order_tags",
        kind="table",
        columns=[
            column("order_id", "bigint", "number", nullable=False),
            column("tag", "text", "string", nullable=False, position=2),
        ],
        constraints=[
            PrimaryKey(name="order_tags_pkey", columns=["order_id", "tag"]),
            ForeignKey(
                name="order_tags_order_fkey",
                columns=["order_id"],
                target_node_id="shop.orders",
                target_columns=["id"],
            ),
        ],
    )

    text = render([model, orders()], "django")

    assert 'order = models.ForeignKey("Orders"' in text
    assert 'unique_together = (("order", "tag"),)' in text


def test_dbml_writes_no_note_when_there_is_nothing_to_note() -> None:
    model = orders().model_copy(
        update={
            "comment": None,
            "constraints": [PrimaryKey(name="pk", columns=["id", "code"])],
        }
    )

    text = render([model], "dbml")

    assert "Note:" not in text
    assert "(id, code) [pk]" in text


def test_django_says_what_it_cannot_do_with_a_composite_key() -> None:
    model = orders().model_copy(
        update={
            "constraints": [PrimaryKey(name="orders_pkey", columns=["id", "code"])]
        }
    )

    text = render([model], "django")

    assert "Django has none" in text
    assert 'unique_together = (("id", "code"),)' in text


# --- DBML --------------------------------------------------------------------


def test_dbml_writes_a_table_per_relation_and_a_ref_per_key() -> None:
    text = render([orders(), customers()], "dbml")

    assert "Table shop.orders {" in text
    assert "Table shop.customers {" in text
    assert "id bigint [pk, increment]" in text
    assert 'code "character varying(30)" [unique]' in text
    assert "Ref: shop.orders.(customer_id) > shop.customers.(id)" in text


def test_dbml_leaves_out_a_key_pointing_outside_the_selection() -> None:
    """dbdiagram refuses a whole file that names a table it was not given."""
    text = render([orders()], "dbml")

    assert "Ref:" not in text


def test_dbml_writes_a_composite_key_as_an_index() -> None:
    model = orders().model_copy(
        update={
            "constraints": [PrimaryKey(name="orders_pkey", columns=["id", "code"])]
        }
    )

    text = render([model], "dbml")

    assert "indexes {" in text
    assert "(id, code) [pk]" in text


# --- the whole document ------------------------------------------------------


def test_every_dialect_names_the_file_it_belongs_in() -> None:
    assert DIALECT_SUFFIX["sqlalchemy"] == ".py"
    assert DIALECT_SUFFIX["django"] == ".py"
    assert DIALECT_SUFFIX["dbml"] == ".dbml"


def test_more_relations_than_the_ceiling_are_refused() -> None:
    many = [
        customers().model_copy(update={"node_id": f"shop.t{index}", "name": f"t{index}"})
        for index in range(201)
    ]

    with pytest.raises(ValueError, match="At most"):
        render(many, "dbml")


def test_a_relation_with_no_schema_is_written_by_its_bare_name() -> None:
    """A Parquet file sits in no schema and still has a model (D51)."""
    model = customers().model_copy(update={"schema_name": None})

    assert "__table_args__" not in render([model], "sqlalchemy")
    assert 'db_table = "customers"' in render([model], "django")
    assert "Table customers {" in render([model], "dbml")
