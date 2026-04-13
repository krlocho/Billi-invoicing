from uuid import UUID
from pydantic import BaseModel


class ChannelResponse(BaseModel):
    id: UUID
    name: str
    code: str

    model_config = {"from_attributes": True}
