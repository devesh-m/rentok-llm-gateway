import secrets
from typing import List
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.db import get_db
from app.models.key import VirtualKey
from app.models.schemas import CreateKeyRequest, VirtualKeyResponse

router = APIRouter(prefix="/v1/admin/keys", tags=["Admin Key Management"])


def verify_admin_key(
    x_admin_key: str = Header(
        default="dev-admin-secret-change-in-production",
        description="Master Admin Secret Key",
    )
):
    if x_admin_key != settings.ADMIN_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Unauthorized: Invalid admin secret key"},
        )
    return x_admin_key


@router.post("", response_model=VirtualKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_virtual_key(
    payload: CreateKeyRequest,
    admin_auth: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new virtual API key with a configured budget cap (in USD)."""
    random_token = secrets.token_hex(16)
    new_key_value = f"gw-live-{random_token}"

    key_record = VirtualKey(
        key_value=new_key_value,
        name=payload.name,
        max_budget=payload.max_budget,
        current_spend=0.00,
        is_active=True,
    )
    db.add(key_record)
    await db.commit()
    await db.refresh(key_record)

    return VirtualKeyResponse(
        id=key_record.id,
        key_value=key_record.key_value,
        name=key_record.name,
        max_budget=key_record.max_budget,
        current_spend=key_record.current_spend,
        remaining_budget=key_record.remaining_budget(),
        is_active=key_record.is_active,
        created_at=key_record.created_at,
    )


@router.get("", response_model=List[VirtualKeyResponse])
async def list_virtual_keys(
    admin_auth: str = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """List all issued virtual API keys with current spend and remaining budgets."""
    result = await db.execute(select(VirtualKey).order_by(VirtualKey.created_at.desc()))
    keys = result.scalars().all()
    return [
        VirtualKeyResponse(
            id=k.id,
            key_value=k.key_value,
            name=k.name,
            max_budget=k.max_budget,
            current_spend=k.current_spend,
            remaining_budget=k.remaining_budget(),
            is_active=k.is_active,
            created_at=k.created_at,
        )
        for k in keys
    ]

