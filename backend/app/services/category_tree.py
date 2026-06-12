"""Hierarchie-Helfer für Kategorien (beliebige Tiefe bis MAX_CATEGORY_DEPTH).

Alle Funktionen sind user-scoped: sie betrachten nur die Kategorien EINES Users,
damit Tiefen-/Nachfahren-Berechnungen nie über User-Grenzen laufen.
"""

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from ..models import Category

# Maximale Verschachtelungstiefe (1 = Hauptkategorie). Muss mit
# MAX_CATEGORY_DEPTH in frontend/js/utils.js übereinstimmen.
MAX_CATEGORY_DEPTH = 5


def _parent_map(db: Session, user_id: int) -> Dict[int, Optional[int]]:
    """id -> parent_id für alle Kategorien eines Users."""
    rows = db.query(Category.id, Category.parent_id).filter(
        Category.user_id == user_id
    ).all()
    return {r.id: r.parent_id for r in rows}


def _children_map(db: Session, user_id: int) -> Dict[Optional[int], List[int]]:
    """parent_id -> [child_ids] für alle Kategorien eines Users."""
    children: Dict[Optional[int], List[int]] = {}
    rows = db.query(Category.id, Category.parent_id).filter(
        Category.user_id == user_id
    ).all()
    for r in rows:
        children.setdefault(r.parent_id, []).append(r.id)
    return children


def get_descendant_ids(db: Session, user_id: int, category_id: int) -> List[int]:
    """Alle Kategorie-IDs unterhalb von category_id (beliebige Tiefe, ohne die Kategorie selbst)."""
    children = _children_map(db, user_id)
    result: List[int] = []
    queue = list(children.get(category_id, []))
    seen = {category_id}
    while queue:
        cid = queue.pop()
        if cid in seen:
            continue
        seen.add(cid)
        result.append(cid)
        queue.extend(children.get(cid, []))
    return result


def get_category_depth(db: Session, user_id: int, category_id: int) -> int:
    """Tiefe einer Kategorie (1 = Hauptkategorie). Zyklusgesichert."""
    parents = _parent_map(db, user_id)
    depth = 1
    seen = {category_id}
    parent = parents.get(category_id)
    while parent is not None and parent not in seen:
        seen.add(parent)
        depth += 1
        parent = parents.get(parent)
    return depth


def get_subtree_height(db: Session, user_id: int, category_id: int) -> int:
    """Höhe des Teilbaums unter category_id (1 = keine Kinder). Zyklusgesichert."""
    children = _children_map(db, user_id)

    def height(cid: int, seen: frozenset) -> int:
        kids = [k for k in children.get(cid, []) if k not in seen]
        if not kids:
            return 1
        return 1 + max(height(k, seen | {k}) for k in kids)

    return height(category_id, frozenset({category_id}))
