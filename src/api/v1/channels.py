from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.database import get_db
from src.models.channel import Channel
from src.models.user import User
from src.schemas.channel import ChannelResponse

router = APIRouter()


@router.get("/", response_model=list[ChannelResponse])
def list_channels(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Channel).filter(Channel.tenant_id == user.tenant_id).all()
