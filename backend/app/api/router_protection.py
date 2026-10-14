import asyncio
import hmac
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.router.base import RouterError
from app.schemas.domain import Domain

router = APIRouter(prefix="/v1/router", tags=["authorized router protection"])


def service(request: Request, authorization: str | None = Header(default=None)):
    value = getattr(request.app.state, "router_protection", None)
    if value is None:
        raise HTTPException(503, "Router Protection is disabled or unavailable. Configure the dedicated DNS service first.")
    if not authorization or not hmac.compare_digest(authorization, "Bearer " + value.settings.token):
        raise HTTPException(401, "A valid Router Protection administrator token is required.")
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Connect(Strict):
    routerUrl: str = Field(max_length=200)
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=256)
    authorized: Literal[True]


class Apply(Strict):
    preview: str = Field(min_length=16, max_length=128)
    authorized: Literal[True]


class PhoneRule(Strict):
    domain: Domain
    action: Literal["block", "allow"]
    includeSubdomains: bool
    updatedAt: int = Field(ge=0)


class Policy(Strict):
    rules: list[PhoneRule] = Field(max_length=10000)


async def work(call, *args):
    try:
        return await asyncio.to_thread(call, *args)
    except RouterError as error:
        raise HTTPException(409, str(error)) from None
    except Exception:
        raise HTTPException(503, "Router action failed. Check its status and recovery instructions; no success was assumed.") from None


@router.get("/status")
def status(value=Depends(service)):
    return value.status()


@router.post("/connect")
async def connect(payload: Connect, value=Depends(service)):
    return await work(value.connect, payload.routerUrl, payload.username, payload.password.get_secret_value(), payload.authorized)


@router.post("/apply")
async def apply(payload: Apply, value=Depends(service)):
    return await work(value.apply, payload.preview, payload.authorized)


@router.post("/verify")
async def verify(value=Depends(service)):
    return await work(value.verify)


@router.post("/stop")
async def stop(value=Depends(service)):
    return await work(value.stop)


@router.post("/policy")
def policy(payload: Policy, value=Depends(service)):
    try:
        value.policy.sync([r.model_dump() for r in payload.rules])
    except ValueError:
        raise HTTPException(422, "Send one complete canonical phone rule per hostname.") from None
    return {"synced": True, "rules": len(payload.rules)}
