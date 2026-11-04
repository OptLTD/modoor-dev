from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modoor.core.db import Base
from modoor.engine.serial import BaseSerial, claim_serial


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[BaseSerial.__table__])
    return Session(engine)


def _add_counter(session: Session, head: str, value: int = 0) -> None:
    session.add(
        BaseSerial(
            id=head,
            tenant=1,
            model="fleet.maintain",
            head=head,
            value=value,
        )
    )
    session.flush()


def test_claim_serial_keeps_date_head() -> None:
    with _session() as session:
        _add_counter(session, "WB20261103")

        assert claim_serial(
            session, tenant=1, model="fleet.maintain", code="WB20261103001"
        )

        rows = session.scalars(select(BaseSerial)).all()
        assert [(row.head, row.value) for row in rows] == [("WB20261103", 1)]


def test_claim_serial_matches_longest_known_head() -> None:
    with _session() as session:
        _add_counter(session, "WB", 7)
        _add_counter(session, "WB20261103", 2)

        assert claim_serial(
            session, tenant=1, model="fleet.maintain", code="WB20261103005"
        )

        values = {
            row.head: row.value for row in session.scalars(select(BaseSerial)).all()
        }
        assert values == {"WB": 7, "WB20261103": 5}


def test_claim_serial_uses_date_mode_when_width_differs() -> None:
    # Existing maintain codes are 3-digit while config counting is 5; date
    # mode must drive the split, not the configured sequence width.
    with _session() as session:
        assert claim_serial(
            session,
            tenant=1,
            model="fleet.maintain",
            code="WB20261103001",
            prefix="WB",
            datetime_mode="ONLYDATE",
            width=5,
        )

        row = session.scalars(select(BaseSerial)).one()
        assert (row.head, row.value) == ("WB20261103", 1)


def test_claim_serial_uses_width_for_unknown_head() -> None:
    with _session() as session:
        assert claim_serial(
            session,
            tenant=1,
            model="fleet.maintain",
            code="WB20261103001",
            width=3,
        )

        row = session.scalars(select(BaseSerial)).one()
        assert (row.head, row.value) == ("WB20261103", 1)


def test_claim_serial_ignores_non_numeric_tail() -> None:
    with _session() as session:
        assert not claim_serial(
            session, tenant=1, model="fleet.maintain", code="WB20261103-A"
        )
