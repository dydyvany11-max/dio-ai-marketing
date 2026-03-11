from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class TelegramSettings:
    api_id: int
    api_hash: str
    session_name: str


def load_settings() -> TelegramSettings:
    load_dotenv()

    api_id = int(os.getenv("TG_API_ID", "0"))
    api_hash = os.getenv("TG_API_HASH", "")
    session_name = os.getenv("TG_SESSION_NAME", "tg_session")

    if not api_id or not api_hash:
        raise RuntimeError("Set TG_API_ID and TG_API_HASH in .env")

    return TelegramSettings(api_id=api_id, api_hash=api_hash, session_name=session_name)
