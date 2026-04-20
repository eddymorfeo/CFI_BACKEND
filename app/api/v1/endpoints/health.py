from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "ok"}

@router.get("/health/db")
def health_db_check(database: Session = Depends(get_db)):
    database.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}