from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..config import tenants, TenantConfig, settings
import json

router = APIRouter()

class AddTenantRequest(BaseModel):
    tenant_id: str
    openai_api_key: str
    document_path: str
    chroma_db_path: str
    prompt: str

@router.post("/add_tenant")
async def add_tenant(request: AddTenantRequest):
    """Add a new tenant configuration."""
    if request.tenant_id in tenants:
        raise HTTPException(status_code=400, detail=f"Tenant {request.tenant_id} already exists")
    
    new_tenant = TenantConfig(
        openai_api_key=request.openai_api_key,
        document_path=request.document_path,
        chroma_db_path=request.chroma_db_path,
        prompt=request.prompt
    )
    
    tenants[request.tenant_id] = new_tenant
    
    # Save to file
    data = {k: v.dict() for k, v in tenants.items()}
    with open(settings.tenants_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    return {"message": f"Tenant {request.tenant_id} added successfully"}
