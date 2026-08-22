from pydantic import BaseModel, ConfigDict


class AccountCreate(BaseModel):
    account_name: str
    platform: str


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_name: str
    platform: str
