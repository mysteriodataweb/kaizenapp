from fastapi import APIRouter

from app.api.v1 import (
    admin,
    applications,
    assist,
    auth,
    calendar,
    dashboard,
    documents,
    health,
    notifications,
    opportunities,
    profile,
)

api_router = APIRouter(prefix="/api/v1")
for module in (
    health,
    auth,
    profile,
    opportunities,
    applications,
    documents,
    notifications,
    dashboard,
    calendar,
    assist,
    admin,
):
    api_router.include_router(module.router)
