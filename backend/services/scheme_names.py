from sqlalchemy.orm import Session

from models.portfolio_scheme import PortfolioScheme


def display_name_for(db: Session, user_id: int, scheme_code: str, fallback: str) -> str:
    """A user's own label for a scheme code, falling back to the AMFI name
    (or the raw code) when they haven't set one.
    """
    ps = (
        db.query(PortfolioScheme)
        .filter(PortfolioScheme.user_id == user_id, PortfolioScheme.scheme_code == scheme_code)
        .first()
    )
    return ps.display_name if ps else fallback
