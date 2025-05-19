import os
from pathlib import Path
from typing import Optional

class Config:
    # Base paths
    BASE_DIR = Path(__file__).parent.parent
    CREDENTIALS_DIR = BASE_DIR / "credentials"
    
    # Google Calendar credentials
    GOOGLE_CREDENTIALS_PATH = os.getenv(
        "GOOGLE_CREDENTIALS_PATH",
        str(CREDENTIALS_DIR / "credentials.json")
    )
    GOOGLE_TOKEN_PATH = os.getenv(
        "GOOGLE_TOKEN_PATH",
        str(CREDENTIALS_DIR / "token.pickle")
    )
    
    @classmethod
    def setup_credentials(cls) -> None:
        """Create credentials directory if it doesn't exist."""
        cls.CREDENTIALS_DIR.mkdir(exist_ok=True)
        
    @classmethod
    def check_credentials(cls) -> bool:
        """Check if credentials file exists."""
        return os.path.exists(cls.GOOGLE_CREDENTIALS_PATH)
    
    @classmethod
    def get_credentials_path(cls) -> Optional[str]:
        """Get the path to credentials file if it exists."""
        if cls.check_credentials():
            return cls.GOOGLE_CREDENTIALS_PATH
        return None 