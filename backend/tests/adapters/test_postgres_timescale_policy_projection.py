from app.adapters.postgres.timescale.reports import REPORTS


def test_jobs_project_only_typed_policy_parameters_after_routine_verification() -> None:
    report = next(report for report in REPORTS if report.public_view == "jobs")
    statement = report.statement.as_string()
    assert "config" in report.required_columns
    assert '"config",' not in statement
    assert "source.config ->>" in statement
    assert "e.extname = 'timescaledb'" in statement
    assert "d.deptype = 'e'" in statement
    assert "p.prokind = 'p'" in statement
    assert "p.proargtypes = '23 3802'" in statement
    assert "pg_catalog.pg_input_is_valid" in statement
    for key in ("drop_after", "compress_after", "start_offset", "end_offset"):
        assert f'AS "{key}_integer"' in statement
        assert f'AS "{key}_interval"' in statement
    assert "err_message" not in statement
    assert "job_errors" not in statement
