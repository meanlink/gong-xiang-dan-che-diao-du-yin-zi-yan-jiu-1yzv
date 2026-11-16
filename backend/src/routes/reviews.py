from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Review
from src.schemas.review import ReviewInput, OpinionInput
from src.middlewares.auth import current_user, can_write, admin_only, reviewer_only, adjudicator_only
from src.services import reviews
from src.services.audit import record
router = APIRouter()

@router.get('/reviews')
def listing(db=Depends(get_db), u=Depends(current_user)):
    return [{'id': r.id, 'name': r.name, 'status': r.status, 'created_at': r.created_at,
             'closed_at': r.closed_at, 'result_dataset_id': r.result_dataset_id,
             'progress': reviews.progress(db, r.id)}
            for r in db.scalars(select(Review).order_by(Review.id.desc()))]

@router.post('/reviews', status_code=201)
def create(data: ReviewInput, db=Depends(get_db), u=Depends(can_write)):
    r = reviews.create(db, data, u)
    record(db, u.email, 'review.create', {'id': r.id, 'items': len(data.indexes) if data.indexes is not None else len(r.frozen_records)})
    db.commit()
    return reviews.detail(db, r.id, u)

@router.get('/reviews/{id}')
def detail(id: int, db=Depends(get_db), u=Depends(current_user)):
    return reviews.detail(db, id, u)

@router.post('/reviews/{id}/claim', status_code=201)
def claim(id: int, db=Depends(get_db), u=Depends(reviewer_only)):
    a, item = reviews.claim(db, id, u)
    record(db, u.email, 'review.claim', {'review': id, 'assignment': a.id, 'idx': item.idx})
    db.commit()
    return {'assignment': {'id': a.id, 'due_at': a.due_at, 'claimed_at': a.claimed_at},
            'item': {'idx': item.idx, 'record': item.record}}

@router.post('/reviews/{id}/claim-adjudication', status_code=201)
def claim_adjudication(id: int, db=Depends(get_db), u=Depends(adjudicator_only)):
    a, item, pair = reviews.claim_adjudication(db, id, u)
    record(db, u.email, 'review.claim_adjudication', {'review': id, 'assignment': a.id, 'idx': item.idx})
    db.commit()
    return {'assignment': {'id': a.id, 'due_at': a.due_at, 'claimed_at': a.claimed_at},
            'item': {'idx': item.idx, 'record': item.record},
            'pair': [{'decision': x.opinion, 'rationale': x.rationale} for x in pair]}

@router.post('/assignments/{id}/submit')
def submit(id: int, data: OpinionInput, db=Depends(get_db), u=Depends(current_user)):
    if u.role not in ('reviewer', 'adjudicator'): raise HTTPException(403, '仅复核员或裁决员可以交卷')
    a, item = reviews.submit(db, id, u, data.decision, data.rationale)
    record(db, u.email, 'review.submit' if a.kind == 'review' else 'review.adjudicate',
           {'assignment': a.id, 'item': item.id, 'decision': data.decision})
    db.commit()
    return {'assignment_id': a.id, 'item_status': item.status, 'final_decision': item.final_decision}

@router.post('/assignments/{id}/reassign')
def reassign(id: int, db=Depends(get_db), u=Depends(admin_only)):
    a = reviews.reassign(db, id)
    record(db, u.email, 'review.reassign', {'assignment': a.id, 'item': a.item_id})
    db.commit()
    return {'assignment_id': a.id, 'status': a.status}

@router.post('/reviews/{id}/close')
def close(id: int, db=Depends(get_db), u=Depends(admin_only)):
    r, dataset = reviews.close(db, id)
    record(db, u.email, 'review.close', {'review': r.id, 'dataset': dataset.id, 'rows': len(dataset.records)})
    db.commit()
    return reviews.detail(db, r.id, u)
