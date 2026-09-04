from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from pydantic.networks import EmailStr
from starlette.concurrency import run_in_threadpool

from app.core.email import generate_test_email, send_email
from app.core.schemas import Message
from app.users.deps import get_current_active_superuser

router = APIRouter(prefix="/utils", tags=["utils"])


@router.post(
    "/test-email/",
    dependencies=[Depends(get_current_active_superuser)],
    status_code=201,
)
async def test_email(email_to: EmailStr) -> Message:
    """
    Test emails.
    """
    email_data = generate_test_email(email_to=email_to)
    # send_email blocks on SMTP: calling it directly from an async handler
    # would stall the whole event loop.
    await run_in_threadpool(
        send_email,
        email_to=email_to,
        subject=email_data.subject,
        html_content=email_data.html_content,
    )
    return Message(message="Test email sent")


@router.get("/health-check/")
async def health_check() -> bool:
    return True


class ServerInfo(BaseModel):
    product: Literal["dataplayer"] = "dataplayer"
    client_api_version: Literal[1] = 1


@router.get("/server-info", response_model=ServerInfo)
async def server_info() -> ServerInfo:
    """Identify a compatible installation before the client sends credentials."""
    return ServerInfo()
