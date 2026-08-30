from app.adapters.delimited import delimiter_of, fit, read_table, usable_names


def test_a_tsv_is_tabs_by_its_name_whatever_its_first_line_looks_like() -> None:
    assert delimiter_of("sample.tsv", "a,b,c") == "\t"


def test_a_csv_is_read_from_its_first_line() -> None:
    assert delimiter_of("sample.csv", "a;b;c") == ";"
    assert delimiter_of("sample.csv", "a,b,c") == ","


def test_a_first_line_that_says_nothing_falls_back_to_a_comma() -> None:
    assert delimiter_of("sample.csv", "one") == ","


def test_a_header_written_by_hand_still_names_every_column() -> None:
    assert usable_names(["id", "", "id", " name "]) == [
        "id",
        "column_2",
        "id_3",
        "name",
    ]


def test_a_short_row_is_padded_and_a_long_one_is_cut_to_the_header() -> None:
    assert fit(["a"], 3) == ["a", None, None]
    assert fit(["a", "b", "c", "d"], 2) == ["a", "b"]


def test_reads_a_whole_table_with_its_header_as_the_column_names() -> None:
    table = read_table("id,code\n7,US\n8,AP\n", "regions.csv", 10)

    assert table.columns == ["id", "code"]
    assert table.rows == [["7", "US"], ["8", "AP"]]
    assert table.more is False


def test_a_value_holding_the_delimiter_stays_one_value() -> None:
    table = read_table('id,name\n1,"Smith, John"\n', "people.csv", 10)

    assert table.rows == [["1", "Smith, John"]]


def test_a_value_holding_a_line_break_stays_one_row() -> None:
    table = read_table('id,note\n1,"first\nsecond"\n', "notes.csv", 10)

    assert table.rows == [["1", "first\nsecond"]]


def test_says_when_the_text_held_more_rows_than_the_ceiling() -> None:
    table = read_table("id\n1\n2\n3\n", "n.csv", 2)

    assert table.rows == [["1"], ["2"]]
    assert table.more is True


def test_a_text_with_no_line_at_all_has_no_columns() -> None:
    table = read_table("", "empty.csv", 10)

    assert table.columns == []
    assert table.rows == []
