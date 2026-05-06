from pydantic import BaseModel, Field


class TenantSettings(BaseModel):
    """Tax and legal settings — vary by country/region (IGIC for Canarias,
    IVA for Spain mainland, VAT for EU, etc.)."""

    tax_type: str = Field(default="IVA", description="IVA, IGIC, VAT, MwSt, TVA, ...")
    tax_rate: float = Field(default=10.0, description="Percentage, e.g. 7.0 for IGIC, 10.0 for IVA reducido")
    country: str | None = None
    region: str | None = None


class TenantResponse(BaseModel):
    id: str
    name: str
    tax_id: str | None = None
    address: str | None = None
    settings: TenantSettings


class TenantUpdate(BaseModel):
    name: str | None = None
    tax_id: str | None = None
    address: str | None = None
    settings: TenantSettings | None = None
