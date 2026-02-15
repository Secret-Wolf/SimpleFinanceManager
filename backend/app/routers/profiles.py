from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..models import Profile, Account
from .. import schemas

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("", response_model=List[schemas.ProfileResponse])
def get_profiles(db: Session = Depends(get_db)):
    """Get all profiles"""
    profiles = db.query(Profile).order_by(Profile.is_admin.desc(), Profile.name).all()
    return profiles


@router.get("/{profile_id}", response_model=schemas.ProfileResponse)
def get_profile(profile_id: int, db: Session = Depends(get_db)):
    """Get single profile"""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profil nicht gefunden")
    return profile


@router.post("", response_model=schemas.ProfileResponse)
def create_profile(data: schemas.ProfileCreate, db: Session = Depends(get_db)):
    """Create a new profile"""
    existing = db.query(Profile).filter(Profile.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Profilname bereits vergeben")

    profile = Profile(
        name=data.name,
        color=data.color or "#2563eb",
        is_admin=False
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.patch("/{profile_id}", response_model=schemas.ProfileResponse)
def update_profile(
    profile_id: int,
    data: schemas.ProfileUpdate,
    db: Session = Depends(get_db)
):
    """Update a profile"""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profil nicht gefunden")

    if data.name is not None:
        existing = db.query(Profile).filter(
            Profile.name == data.name, Profile.id != profile_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Profilname bereits vergeben")
        profile.name = data.name

    if data.color is not None:
        profile.color = data.color

    db.commit()
    db.refresh(profile)
    return profile


@router.delete("/{profile_id}")
def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    """Delete a profile (cannot delete admin profile)"""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profil nicht gefunden")

    if profile.is_admin:
        raise HTTPException(status_code=400, detail="Admin-Profil kann nicht gelöscht werden")

    # Unlink accounts from this profile
    db.query(Account).filter(Account.profile_id == profile_id).update(
        {"profile_id": None}, synchronize_session=False
    )

    db.delete(profile)
    db.commit()
    return {"message": "Profil gelöscht"}
