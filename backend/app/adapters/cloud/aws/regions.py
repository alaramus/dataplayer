"""Amazon's regions, offered by the field that names one (D461).

An account's are asked of EC2: the regions it has enabled. Without an account,
or when it may not ask, the list is the one Amazon publishes for everybody —
the regions of its IP ranges, read without credentials and kept a day. When
neither answers, botocore's own list stands in, so an offline server still
offers the regions it was shipped knowing. What each region is called comes
from botocore too: neither of Amazon's answers says it.
"""

import logging
import re
import threading
import time
from typing import Any

import httpx
from botocore.exceptions import BotoCoreError, ClientError
from botocore.loaders import create_loader

from app.adapters.cloud import Region
from app.adapters.protocol import AdapterError

logger = logging.getLogger(__name__)

PUBLISHED = "https://ip-ranges.amazonaws.com/ip-ranges.json"
KEPT_SECONDS = 24 * 3600.0
# The partitions an ordinary account lives in; the isolated ones are not
# reached from here and only crowd the list.
_PARTITIONS = ("aws", "aws-us-gov", "aws-cn", "aws-eusc")
# A region's name, as both answers spell one; `GLOBAL` and anything else are not.
_NAME = re.compile(r"^[a-z]{2,4}(-[a-z]+)+-\d+$")

_lock = threading.Lock()
_published: tuple[float, list[str]] | None = None
_titles: dict[str, str] | None = None


def account_regions(session: Any, config: Any) -> list[Region]:
    """The regions an account has enabled, or Amazon's published list when
    it may not ask EC2. A refusal is not said: the list is a convenience, and
    the account's own test is where a wrong key is found."""
    try:
        found = session.client("ec2", config=config).describe_regions()
    except (ClientError, BotoCoreError, AdapterError) as failure:
        logger.info("EC2 did not list the account's regions: %s", type(failure).__name__)
        return published_regions()
    names = [str(one.get("RegionName", "")) for one in found.get("Regions", [])]
    return _titled(names) or published_regions()


def published_regions() -> list[Region]:
    """Every region Amazon publishes, kept a day; botocore's when it does not answer."""
    global _published
    with _lock:
        if _published is not None and time.monotonic() - _published[0] < KEPT_SECONDS:
            return _titled(_published[1])
    try:
        names = _from_ip_ranges(_fetch())
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as failure:
        logger.info("Amazon's published regions did not arrive: %s", type(failure).__name__)
        return _titled(list(_known()))
    with _lock:
        _published = (time.monotonic(), names)
    return _titled(names)


def _fetch() -> Any:
    response = httpx.get(PUBLISHED, timeout=10.0)
    response.raise_for_status()
    return response.json()


def _from_ip_ranges(data: Any) -> list[str]:
    names = {
        str(prefix["region"])
        for key in ("prefixes", "ipv6_prefixes")
        for prefix in data.get(key, [])
    }
    found = [name for name in names if _NAME.match(name)]
    if not found:
        raise ValueError("no regions")
    return found


def _known() -> dict[str, str]:
    """botocore's regions and their titles, read once."""
    global _titles
    if _titles is None:
        partitions = create_loader().load_data("partitions")["partitions"]
        _titles = {
            name: str(region.get("description", ""))
            for partition in partitions
            if partition["id"] in _PARTITIONS
            for name, region in partition["regions"].items()
            if _NAME.match(name)
        }
    return _titles


def _titled(names: list[str]) -> list[Region]:
    titles = _known()
    return [Region(name=name, title=titles.get(name, "")) for name in sorted(set(names)) if _NAME.match(name)]

