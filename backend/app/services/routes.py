from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.adapters import registry
from app.services import templates
from app.users.deps import get_current_user

# Authentication on the router, as `adapter-types` declares it: the handler
# does not use the user, and an unused argument is a lint error.
#
# The tag has no hyphen for the same reason that one does not: the client
# generator cuts the method name at the first hyphen of the operation id.
router = APIRouter(
    prefix="/services",
    tags=["services"],
    dependencies=[Depends(get_current_user)],
)


class ServiceTemplateInfo(BaseModel):
    """One service this server may be asked to start.

    What a client is allowed to know: which key names it, what will run, and
    what it becomes. Not the container it would create — that is decided by
    the server and is nothing a request may steer, so publishing it would only
    invite the belief that it can.
    """

    key: str
    title: str
    description: str
    # The exact image, so somebody deciding whether to press the button can
    # see what would be pulled onto the machine.
    image: str
    container_port: int
    # What the ready service becomes, in both the name routes use and the
    # words the adapter calls itself by. Sent rather than joined on the client
    # against the adapter-types list: one name for a source type, and it is
    # the server's.
    adapter_type: str
    adapter_title: str
    # Which credentials this server makes up. A statement about what a person
    # will not be asked for, which is the whole difference from the old form.
    generated: list[templates.CredentialSlot]


@router.get("/templates", response_model=list[ServiceTemplateInfo])
async def read_service_templates() -> Any:
    """
    List the services this server can start, and what each one becomes.

    A closed set written in code. A client picks a key from it; nothing about
    the container is a request's to choose (D80).
    """
    return [
        ServiceTemplateInfo(
            key=template.key,
            title=template.title,
            description=template.description,
            image=template.image,
            container_port=template.container_port,
            adapter_type=template.adapter_type,
            adapter_title=registry.get(template.adapter_type).title,
            generated=list(templates.generated_slots(template)),
        )
        for template in templates.all_templates()
    ]
