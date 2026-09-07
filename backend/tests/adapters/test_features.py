from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.adapters.features import SourceFeature, SourceFeatures


def test_available_feature_requires_an_installed_version() -> None:
    with pytest.raises(ValidationError):
        SourceFeature(code="timescaledb", title="TimescaleDB", state="available")


def test_unknown_feature_state_requires_a_safe_reason() -> None:
    with pytest.raises(ValidationError):
        SourceFeature(
            code="timescaledb",
            title="TimescaleDB",
            installed_version="2.18.0",
            state="unsupported",
        )


def test_feature_codes_are_unique() -> None:
    feature = SourceFeature(
        code="timescaledb",
        title="TimescaleDB",
        installed_version="2.18.0",
        state="available",
    )

    with pytest.raises(ValidationError):
        SourceFeatures(
            observed_at=datetime(2026, 9, 7, tzinfo=UTC),
            features=[feature, feature],
        )
