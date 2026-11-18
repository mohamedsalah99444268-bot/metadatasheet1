from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import FieldReview, ParsedField
from ..schemas import (
    FieldReviewBulkRequest,
    FieldReviewOut,
    FieldReviewUpdate,
)

router = APIRouter(prefix="/api/validation", tags=["validation"])


def _clean_value(value: str) -> str:
    if not value.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="value must not be empty",
        )
    return value


@router.get("/reviews", response_model=list[FieldReviewOut])
def list_reviews(document_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(FieldReview)
    if document_id is not None:
        query = query.join(
            ParsedField, FieldReview.field_id == ParsedField.id
        ).filter(ParsedField.document_id == document_id)
    return query.order_by(FieldReview.field_id).all()


@router.put("/reviews/{field_id}", response_model=FieldReviewOut)
def upsert_review(
    field_id: int,
    payload: FieldReviewUpdate,
    db: Session = Depends(get_db),
):
    value = _clean_value(payload.value)
    field = db.query(ParsedField).filter(ParsedField.id == field_id).first()
    if field is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Parsed field not found"
        )
    review = db.query(FieldReview).filter(FieldReview.field_id == field_id).first()
    if review is None:
        review = FieldReview(field_id=field_id, value=value, status=payload.status)
        db.add(review)
    else:
        review.value = value
        review.status = payload.status
    db.commit()
    db.refresh(review)
    return review


@router.post("/reviews/bulk", response_model=list[FieldReviewOut])
def bulk_upsert_reviews(
    payload: FieldReviewBulkRequest,
    db: Session = Depends(get_db),
):
    items = payload.items
    field_ids = {item.field_id for item in items}
    existing_field_ids: set[int] = set()
    if field_ids:
        existing_field_ids = {
            row.id
            for row in db.query(ParsedField.id)
            .filter(ParsedField.id.in_(field_ids))
            .all()
        }
    reviews = {
        review.field_id: review
        for review in db.query(FieldReview)
        .filter(FieldReview.field_id.in_(field_ids))
        .all()
    } if field_ids else {}

    results: dict[int, FieldReview] = {}
    for item in items:
        if item.field_id not in existing_field_ids:
            continue
        value = _clean_value(item.value)
        review = reviews.get(item.field_id)
        if review is None:
            review = FieldReview(field_id=item.field_id, value=value, status=item.status)
            db.add(review)
            reviews[item.field_id] = review
        else:
            review.value = value
            review.status = item.status
        results[item.field_id] = review

    db.commit()
    for review in results.values():
        db.refresh(review)
    return [results[field_id] for field_id in sorted(results)]


@router.delete("/reviews/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(field_id: int, db: Session = Depends(get_db)):
    db.query(FieldReview).filter(FieldReview.field_id == field_id).delete(
        synchronize_session=False
    )
    db.commit()
    return None


@router.delete("/reviews")
def delete_all_reviews(db: Session = Depends(get_db)):
    deleted = db.query(FieldReview).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}
