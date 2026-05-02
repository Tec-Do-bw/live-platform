from typing import Optional

from pydantic import BaseModel


class CreateBrowserRequest(BaseModel):
    country: str
    media: str
    validate_id: str
    live_account: str
    advertiser_name: Optional[str] = None
    live_room_url: Optional[str] = None
    collection_id: Optional[str] = None


class CloseBrowserRequest(BaseModel):
    session_id: str
    collection_id: Optional[str] = None
