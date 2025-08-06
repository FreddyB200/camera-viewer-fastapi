# file: settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # This tells Pydantic to read variables from a file named .env
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # Define the variables with their expected types.
    # If any of these are missing in the .env file, the app will fail to start.
    CAM_USER: str
    CAM_PASS: str
    CAM_IP: str
    CAM_PORT: int
    TOTAL_CAMERAS: int

# Create a single, reusable instance of the settings that we can import elsewhere
settings = Settings()