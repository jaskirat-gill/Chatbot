from pydantic_settings import BaseSettings
import json
import os
from typing import Dict
from pydantic import BaseModel

class TenantConfig(BaseModel):
    openai_api_key: str
    document_path: str
    prompt: str
    pinecone_namespace: str

class Settings(BaseSettings):
    openai_api_key: str
    frontend_origins: str = "*"
    tenants_file: str = "tenants.json"
    pinecone_api_key: str
    pinecone_environment: str
    pinecone_index_name: str

    class Config:
        env_file = ".env"

    def load_tenants(self) -> Dict[str, TenantConfig]:
        with open(self.tenants_file, 'r') as f:
            data = json.load(f)
        tenants_dict = {}
        for k, v in data.items():
            if not v.get('openai_api_key') or v['openai_api_key'] == 'default':
                # Check for tenant-specific API key
                tenant_env_key = os.getenv(f"OPENAI_API_KEY_{k.upper()}")
                v['openai_api_key'] = tenant_env_key or self.openai_api_key
            tenants_dict[k] = TenantConfig(**v)
        return tenants_dict

settings = Settings()
tenants = settings.load_tenants()
