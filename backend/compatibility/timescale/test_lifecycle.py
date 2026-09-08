from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID
from app.adapters.postgres.system_reports import SECTION_ID
from compatibility.timescale.source import TimescaleSource


async def test_new_adapter_observes_extension_install_and_removal(
    source: TimescaleSource,
) -> None:
    database = "lifecycle_fixture"
    session = source.session(database=database)
    assert await session.query("SELECT ready FROM public.fixture_marker") == [{"ready": 1}]
    before = source.adapter(database=database)
    assert (await before.source_features()).features[0].state == "absent"
    assert TIMESCALE_SECTION_ID not in {
        node.id for node in await before.list_children(SECTION_ID)
    }

    await session.schema_change("CREATE EXTENSION timescaledb")
    try:
        installed = source.adapter(database=database)
        feature = (await installed.source_features()).features[0]
        assert feature.state == "available" and feature.installed_version == source.version
        assert TIMESCALE_SECTION_ID in {
            node.id for node in await installed.list_children(SECTION_ID)
        }
        # Discovery is shared within a request, never across fresh adapters (D120).
        assert (await before.source_features()).features[0].state == "absent"
    finally:
        await session.schema_change("DROP EXTENSION timescaledb")

    removed = source.adapter(database=database)
    feature = (await removed.source_features()).features[0]
    assert feature.state == "absent" and feature.installed_version is None
    assert TIMESCALE_SECTION_ID not in {
        node.id for node in await removed.list_children(SECTION_ID)
    }
    assert await session.query("SELECT ready FROM public.fixture_marker") == [{"ready": 1}]
    assert (await source.adapter().source_features()).features[0].state == "available"
    assert (await source.adapter(database="plain_fixture").source_features()).features[0].state == "absent"
