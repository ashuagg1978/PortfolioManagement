from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import get_current_user
from api.routes.accounts import router as accounts_router
from api.routes.advisor import router as advisor_router
from api.routes.auth import router as auth_router
from api.routes.dashboard import router as dashboard_router
from api.routes.health import router as health_router
from api.routes.imports import router as imports_router
from api.routes.nav import router as nav_router
from api.routes.sips import router as sips_router
from api.routes.transactions import router as transactions_router
from core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Mutual funds portfolio manager: transactions, NAV sync, XIRR, and SIP tracking.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
# Login is public and the admin endpoints check their own dependency;
# everything else under /api requires a valid token.
app.include_router(auth_router, prefix=settings.api_prefix)
protected = [Depends(get_current_user)]
app.include_router(accounts_router, prefix=settings.api_prefix, dependencies=protected)
app.include_router(advisor_router, prefix=settings.api_prefix, dependencies=protected)
app.include_router(nav_router, prefix=settings.api_prefix, dependencies=protected)
app.include_router(transactions_router, prefix=settings.api_prefix, dependencies=protected)
app.include_router(dashboard_router, prefix=settings.api_prefix, dependencies=protected)
app.include_router(sips_router, prefix=settings.api_prefix, dependencies=protected)
app.include_router(imports_router, prefix=settings.api_prefix, dependencies=protected)
