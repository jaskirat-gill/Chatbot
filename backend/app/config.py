from pydantic_settings import BaseSettings
from pydantic import BaseModel
import json
from typing import Dict

class TenantConfig(BaseModel):
    openai_api_key: str
    document_path: str
    prompt: str
    pinecone_namespace: str

class Settings(BaseSettings):
    # Public domain for Twilio webhooks (e.g., "your-app.ondigitalocean.app")
    base_url: str = ""

    openai_api_key: str
    frontend_origins: str = "*"
    tenants_file: str = "tenants.json"
    pinecone_api_key: str
    pinecone_environment: str
    pinecone_index_name: str

    # Voice service API keys
    deepgram_api_key: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""

    model_config = {
        "env_file": ".env",
        "extra": "ignore"  # Ignore any extra fields in .env
    }

    def load_tenants(self) -> Dict[str, TenantConfig]:
        with open(self.tenants_file, 'r') as f:
            data = json.load(f)
        tenants_dict = {}
        for k, v in data.items():
            if not v.get('openai_api_key') or v['openai_api_key'] == 'default':
                v['openai_api_key'] = self.openai_api_key
            tenants_dict[k] = TenantConfig(**v)
        return tenants_dict

settings = Settings()
tenants = settings.load_tenants()