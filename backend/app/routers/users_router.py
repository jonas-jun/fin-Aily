"""
users_router.py
───────────────
사용자 프로필 조회 및 수정 엔드포인트.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.dependencies import get_current_user, get_db

router = APIRouter(prefix="/users", tags=["users"])


class UserProfile(BaseModel):
    id: str
    email: str
    display_name: str | None
    preferred_language: str
    created_at: str


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    preferred_language: str | None = None


@router.get("/me", response_model=UserProfile, summary="내 프로필 조회")
async def get_me(
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    res = (
        await db.table("users")
        .select("*")
        .eq("id", str(user.id))
        .limit(1)
        .execute()
    )
    if not res.data:
        # Supabase Auth에는 있지만 users 프로필 테이블에 없는 경우 → 자동 생성
        await db.table("users").insert({
            "id": str(user.id),
            "email": user.email,
            "display_name": None,
            "preferred_language": "ko",
        }).execute()
        return UserProfile(
            id=str(user.id),
            email=user.email,
            display_name=None,
            preferred_language="ko",
            created_at="",
        )

    row = res.data[0]
    return UserProfile(
        id=row["id"],
        email=row["email"],
        display_name=row.get("display_name"),
        preferred_language=row.get("preferred_language", "ko"),
        created_at=str(row.get("created_at", "")),
    )


@router.patch("/me", response_model=UserProfile, summary="프로필 수정")
async def update_me(
    body: UpdateProfileRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    updates: dict = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name
    if body.preferred_language is not None:
        if body.preferred_language not in ("ko", "en"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_LANGUAGE", "message": "지원 언어는 'ko' 또는 'en'입니다."},
            )
        updates["preferred_language"] = body.preferred_language

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NOTHING_TO_UPDATE", "message": "변경할 항목이 없습니다."},
        )

    res = (
        await db.table("users")
        .update(updates)
        .eq("id", str(user.id))
        .select("*")
        .execute()
    )

    row = res.data[0]
    return UserProfile(
        id=row["id"],
        email=row["email"],
        display_name=row.get("display_name"),
        preferred_language=row.get("preferred_language", "ko"),
        created_at=str(row.get("created_at", "")),
    )
