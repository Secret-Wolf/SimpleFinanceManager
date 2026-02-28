"""Household management endpoints"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..auth import get_current_user
from ..models import User, Household, HouseholdMember, HouseholdInvite
from .. import schemas

router = APIRouter(prefix="/api/households", tags=["households"])


@router.post("", response_model=schemas.HouseholdResponse, status_code=201)
def create_household(
    data: schemas.HouseholdCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new household"""
    name = data.name.strip()
    if not name or len(name) < 2:
        raise HTTPException(status_code=400, detail="Name muss mindestens 2 Zeichen lang sein")

    household = Household(
        name=name,
        created_by=current_user.id,
    )
    db.add(household)
    db.flush()

    # Creator becomes admin member
    member = HouseholdMember(
        household_id=household.id,
        user_id=current_user.id,
        role="admin",
    )
    db.add(member)
    db.commit()
    db.refresh(household)

    return household


@router.get("", response_model=List[schemas.HouseholdDetailResponse])
def get_households(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all households the current user is a member of"""
    memberships = db.query(HouseholdMember).filter(
        HouseholdMember.user_id == current_user.id
    ).all()

    household_ids = [m.household_id for m in memberships]
    if not household_ids:
        return []

    households = db.query(Household).filter(
        Household.id.in_(household_ids)
    ).order_by(Household.created_at).all()

    result = []
    for h in households:
        members = db.query(HouseholdMember).filter(
            HouseholdMember.household_id == h.id
        ).all()

        member_list = []
        for m in members:
            user = db.query(User).filter(User.id == m.user_id).first()
            member_list.append(schemas.HouseholdMemberResponse(
                id=m.id,
                household_id=m.household_id,
                user_id=m.user_id,
                user_email=user.email if user else None,
                user_display_name=user.display_name if user else None,
                role=m.role,
                joined_at=m.joined_at,
            ))

        result.append(schemas.HouseholdDetailResponse(
            id=h.id,
            name=h.name,
            created_by=h.created_by,
            created_at=h.created_at,
            members=member_list,
        ))

    return result


@router.get("/invites", response_model=List[schemas.HouseholdInviteResponse])
def get_my_invites(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get pending invites for the current user"""
    invites = db.query(HouseholdInvite).filter(
        HouseholdInvite.invited_email == current_user.email,
        HouseholdInvite.status == "pending",
    ).order_by(HouseholdInvite.created_at.desc()).all()

    result = []
    for inv in invites:
        household = db.query(Household).filter(Household.id == inv.household_id).first()
        inviter = db.query(User).filter(User.id == inv.invited_by).first()
        result.append(schemas.HouseholdInviteResponse(
            id=inv.id,
            household_id=inv.household_id,
            household_name=household.name if household else None,
            invited_by=inv.invited_by,
            invited_by_name=inviter.display_name if inviter else None,
            invited_email=inv.invited_email,
            status=inv.status,
            created_at=inv.created_at,
        ))

    return result


@router.get("/{household_id}", response_model=schemas.HouseholdDetailResponse)
def get_household(
    household_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get household details"""
    # Verify membership
    membership = db.query(HouseholdMember).filter(
        HouseholdMember.household_id == household_id,
        HouseholdMember.user_id == current_user.id,
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Haushalt nicht gefunden")

    household = db.query(Household).filter(Household.id == household_id).first()
    if not household:
        raise HTTPException(status_code=404, detail="Haushalt nicht gefunden")

    members = db.query(HouseholdMember).filter(
        HouseholdMember.household_id == household_id
    ).all()

    member_list = []
    for m in members:
        user = db.query(User).filter(User.id == m.user_id).first()
        member_list.append(schemas.HouseholdMemberResponse(
            id=m.id,
            household_id=m.household_id,
            user_id=m.user_id,
            user_email=user.email if user else None,
            user_display_name=user.display_name if user else None,
            role=m.role,
            joined_at=m.joined_at,
        ))

    return schemas.HouseholdDetailResponse(
        id=household.id,
        name=household.name,
        created_by=household.created_by,
        created_at=household.created_at,
        members=member_list,
    )


@router.post("/{household_id}/invite", response_model=schemas.HouseholdInviteResponse)
def invite_to_household(
    household_id: int,
    data: schemas.HouseholdInviteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Invite a user to a household"""
    # Verify membership
    membership = db.query(HouseholdMember).filter(
        HouseholdMember.household_id == household_id,
        HouseholdMember.user_id == current_user.id,
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Haushalt nicht gefunden")

    email = data.email.strip().lower()

    # Check if user exists
    invited_user = db.query(User).filter(User.email == email).first()
    if not invited_user:
        raise HTTPException(status_code=404, detail="Benutzer mit dieser E-Mail nicht gefunden")

    # Check if already a member
    existing_member = db.query(HouseholdMember).filter(
        HouseholdMember.household_id == household_id,
        HouseholdMember.user_id == invited_user.id,
    ).first()
    if existing_member:
        raise HTTPException(status_code=400, detail="Benutzer ist bereits Mitglied")

    # Check for pending invite
    existing_invite = db.query(HouseholdInvite).filter(
        HouseholdInvite.household_id == household_id,
        HouseholdInvite.invited_email == email,
        HouseholdInvite.status == "pending",
    ).first()
    if existing_invite:
        raise HTTPException(status_code=400, detail="Einladung bereits gesendet")

    invite = HouseholdInvite(
        household_id=household_id,
        invited_by=current_user.id,
        invited_email=email,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    household = db.query(Household).filter(Household.id == household_id).first()

    return schemas.HouseholdInviteResponse(
        id=invite.id,
        household_id=invite.household_id,
        household_name=household.name if household else None,
        invited_by=invite.invited_by,
        invited_by_name=current_user.display_name,
        invited_email=invite.invited_email,
        status=invite.status,
        created_at=invite.created_at,
    )


@router.post("/invites/{invite_id}/accept")
def accept_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Accept a household invite"""
    invite = db.query(HouseholdInvite).filter(
        HouseholdInvite.id == invite_id,
        HouseholdInvite.invited_email == current_user.email,
        HouseholdInvite.status == "pending",
    ).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Einladung nicht gefunden")

    # Add as member
    member = HouseholdMember(
        household_id=invite.household_id,
        user_id=current_user.id,
        role="member",
    )
    db.add(member)

    invite.status = "accepted"
    db.commit()

    return {"message": "Einladung angenommen"}


@router.post("/invites/{invite_id}/decline")
def decline_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Decline a household invite"""
    invite = db.query(HouseholdInvite).filter(
        HouseholdInvite.id == invite_id,
        HouseholdInvite.invited_email == current_user.email,
        HouseholdInvite.status == "pending",
    ).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Einladung nicht gefunden")

    invite.status = "declined"
    db.commit()

    return {"message": "Einladung abgelehnt"}


@router.delete("/{household_id}/members/{user_id}")
def remove_member(
    household_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a member from a household (admin or self)"""
    # Verify current user is a member
    my_membership = db.query(HouseholdMember).filter(
        HouseholdMember.household_id == household_id,
        HouseholdMember.user_id == current_user.id,
    ).first()
    if not my_membership:
        raise HTTPException(status_code=404, detail="Haushalt nicht gefunden")

    # Can remove self, or admin can remove others
    if user_id != current_user.id and my_membership.role != "admin":
        raise HTTPException(status_code=403, detail="Nur Admins koennen andere Mitglieder entfernen")

    target_membership = db.query(HouseholdMember).filter(
        HouseholdMember.household_id == household_id,
        HouseholdMember.user_id == user_id,
    ).first()
    if not target_membership:
        raise HTTPException(status_code=404, detail="Mitglied nicht gefunden")

    db.delete(target_membership)

    # If no members left, delete the household
    remaining = db.query(HouseholdMember).filter(
        HouseholdMember.household_id == household_id
    ).count()
    if remaining == 0:
        household = db.query(Household).filter(Household.id == household_id).first()
        if household:
            db.delete(household)

    db.commit()

    return {"message": "Mitglied entfernt"}
