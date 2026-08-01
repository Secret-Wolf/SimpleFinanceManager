"""Tags (Schlagworte) für Transaktionen — z.B. "Steuerrelevant" für die Steuererklärung.

Tags sind strikt benutzer-eigen (user_id); Zuweisung an Transaktionen läuft über
PATCH /api/transactions/{id} (tag_ids), Filterung über GET /api/transactions?tag_id=…
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import schemas
from ..audit import log_data_event
from ..auth import get_current_user
from ..database import get_db
from ..models import Tag, User, transaction_tags

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=List[schemas.TagResponse])
def get_tags(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Alle Tags des Benutzers inkl. Anzahl zugewiesener Transaktionen"""
    rows = (
        db.query(Tag, func.count(transaction_tags.c.transaction_id))
        .outerjoin(transaction_tags, Tag.id == transaction_tags.c.tag_id)
        .filter(Tag.user_id == current_user.id)
        .group_by(Tag.id)
        .order_by(Tag.name)
        .all()
    )
    return [
        schemas.TagResponse(id=t.id, name=t.name, color=t.color, transaction_count=count)
        for t, count in rows
    ]


def _find_duplicate(db: Session, user_id: int, name: str, exclude_id: int = None):
    query = db.query(Tag).filter(
        Tag.user_id == user_id,
        func.lower(Tag.name) == name.lower(),
    )
    if exclude_id is not None:
        query = query.filter(Tag.id != exclude_id)
    return query.first()


@router.post("", response_model=schemas.TagResponse, status_code=201)
def create_tag(
    data: schemas.TagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Neues Tag anlegen (Name pro Benutzer eindeutig, case-insensitive)"""
    if _find_duplicate(db, current_user.id, data.name):
        raise HTTPException(status_code=400, detail="Ein Tag mit diesem Namen existiert bereits")

    tag = Tag(user_id=current_user.id, name=data.name, color=data.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)

    log_data_event("create", user_id=current_user.id, resource="tag",
                   resource_id=tag.id, detail=f"name={tag.name}")

    return schemas.TagResponse(id=tag.id, name=tag.name, color=tag.color, transaction_count=0)


@router.patch("/{tag_id}", response_model=schemas.TagResponse)
def update_tag(
    tag_id: int,
    data: schemas.TagUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tag umbenennen / Farbe ändern"""
    tag = db.query(Tag).filter(Tag.id == tag_id, Tag.user_id == current_user.id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag nicht gefunden")

    if data.name is not None:
        if _find_duplicate(db, current_user.id, data.name, exclude_id=tag.id):
            raise HTTPException(status_code=400, detail="Ein Tag mit diesem Namen existiert bereits")
        tag.name = data.name

    if data.color is not None:
        tag.color = data.color or None

    db.commit()
    db.refresh(tag)

    count = (
        db.query(func.count(transaction_tags.c.transaction_id))
        .filter(transaction_tags.c.tag_id == tag.id)
        .scalar()
    )
    return schemas.TagResponse(id=tag.id, name=tag.name, color=tag.color, transaction_count=count)


@router.delete("/{tag_id}")
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tag löschen (entfernt auch alle Zuweisungen; Transaktionen bleiben unberührt)"""
    tag = db.query(Tag).filter(Tag.id == tag_id, Tag.user_id == current_user.id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag nicht gefunden")

    removed = db.execute(
        transaction_tags.delete().where(transaction_tags.c.tag_id == tag.id)
    ).rowcount
    db.delete(tag)
    db.commit()

    log_data_event("delete", user_id=current_user.id, resource="tag",
                   resource_id=tag_id, detail=f"name={tag.name} assignments_removed={removed}")

    return {"message": "Tag gelöscht", "assignments_removed": removed}
