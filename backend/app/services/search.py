"""What this server can start, as the search finds a source type by it (D119).

Handed to the search at assembly: the engine sits below services and imports
no feature (D197).
"""

from app.search.source_types import Startable
from app.services import templates


def startable() -> list[Startable]:
    return [
        Startable(
            adapter_type=template.adapter_type,
            title=template.title,
            description=template.description,
        )
        for template in templates.all_templates()
    ]
