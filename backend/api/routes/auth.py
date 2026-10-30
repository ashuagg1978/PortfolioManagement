from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import get_current_user, require_admin
from core.security import create_access_token, hash_password, verify_password
from db.session import get_db
from models.user import User
from schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)
from services import login_throttle

# Registered WITHOUT the router-wide auth dependency (login must be public);
# the endpoints below that need a user declare it themselves.
router = APIRouter(tags=["auth"])

# Verified against when the username is unknown, so response time doesn't
# reveal which usernames exist.
_DUMMY_HASH = hash_password("unknown-user")


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    ip = request.client.host if request.client else "unknown"
    wait = login_throttle.seconds_locked(ip, payload.username)
    if wait:
        raise HTTPException(
            status_code=429, detail=f"Too many failed attempts. Try again in {wait} seconds."
        )
    user = db.query(User).filter(User.email == payload.username.strip()).first()
    password_ok = verify_password(payload.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok or not user.is_active:
        login_throttle.record_failure(ip, payload.username)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    login_throttle.record_success(ip, payload.username)
    return LoginResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/auth/change-password", status_code=204)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    db.commit()


# --- admin: user management ---


@router.get("/admin/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> list[User]:
    return db.query(User).order_by(User.email).all()


@router.post("/admin/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)
) -> User:
    user = User(
        name=payload.name.strip(),
        email=payload.email.strip(),
        password_hash=hash_password(payload.password),
        is_admin=payload.is_admin,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"User {payload.email.strip()!r} already exists.") from exc
    db.refresh(user)
    return user


@router.patch("/admin/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and (payload.is_active is False or payload.is_admin is False):
        raise HTTPException(status_code=400, detail="You cannot deactivate or demote your own account.")
    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return user
