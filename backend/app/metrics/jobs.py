"""Starting the metrics store as a service (D126).

The service job with its last step replaced: the ready TimescaleDB becomes the
installation's store setting rather than somebody's connection, so its
password has one home and it is not that home's owner's to browse.
"""

from typing import ClassVar

from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import registry
from app.connectors.service import split_options
from app.core.translation import N_
from app.jobs.models import JobKind
from app.jobs.runner import JobHandler
from app.metrics import crud
from app.services.engine import ServiceEngine
from app.services.jobs import CreateService
from app.services.models import ManagedService
from app.services.plan import ServicePlan
from app.services.readiness import ReadinessProbe, wait_until_ready


class CreateMetricsStore(CreateService):
    kind: ClassVar[JobKind] = "metrics.store.create"
    steps: ClassVar[tuple[str, ...]] = (
        N_("clearing an earlier attempt"),
        N_("pulling the image"),
        N_("creating the container"),
        N_("starting the container"),
        N_("waiting for it to answer"),
        N_("saving the metrics store"),
    )

    async def _deliver(
        self,
        session: AsyncSession,
        service: ManagedService,
        plan: ServicePlan,
        options: dict[str, str | int],
    ) -> None:
        kind = registry.get(plan.template.adapter_type)
        config, secrets = split_options(kind, dict(options))
        await crud.save_store_setting(
            session,
            config=config,
            secrets=secrets,
            service_id=service.id,
            configured_by=service.owner_id,
        )
        service.chosen_password = None


def handlers(
    engine: ServiceEngine, probe: ReadinessProbe = wait_until_ready
) -> dict[str, JobHandler]:
    made = CreateMetricsStore(engine, probe)
    return {made.kind: made}
