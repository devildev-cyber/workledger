import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import RequestCounter, WorkOrderCounter

Counter = type[RequestCounter] | type[WorkOrderCounter]


class NumberingError(Exception):
    """Two people started the first record of an organization at the same instant."""


def next_number(db: Session, counter: Counter, organization_id: uuid.UUID) -> int:
    """Give out the next number for an organization.

    The UPDATE locks the counter row until the transaction ends, so two records created at
    once can never receive the same number. Counter rows are created with the organization;
    the insert below only covers organizations that somehow lack one.
    """
    if db.get(counter, organization_id) is None:
        db.add(counter(organization_id=organization_id, last_number=0))
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise NumberingError("Please try again") from None
    db.execute(
        update(counter)
        .where(counter.organization_id == organization_id)
        .values(last_number=counter.last_number + 1)
    )
    number = db.scalar(
        select(counter.last_number).where(counter.organization_id == organization_id)
    )
    assert number is not None
    return number
