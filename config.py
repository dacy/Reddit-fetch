import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    reddit_client_id: str
    reddit_client_secret: str
    reddit_username: str
    reddit_password: str
    anthropic_api_key: str
    user_agent: str = "RedditBusinessValidator/1.0 (by u/your_username)"

    @classmethod
    def from_env(cls) -> "Config":
        required = [
            "REDDIT_CLIENT_ID",
            "REDDIT_CLIENT_SECRET",
            "REDDIT_USERNAME",
            "REDDIT_PASSWORD",
            "ANTHROPIC_API_KEY",
        ]
        missing = [k for k in required if not os.getenv(k)]
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                f"Copy .env.example to .env and fill in your credentials."
            )
        return cls(
            reddit_client_id=os.environ["REDDIT_CLIENT_ID"],
            reddit_client_secret=os.environ["REDDIT_CLIENT_SECRET"],
            reddit_username=os.environ["REDDIT_USERNAME"],
            reddit_password=os.environ["REDDIT_PASSWORD"],
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            user_agent=f"RedditBusinessValidator/1.0 (by u/{os.environ['REDDIT_USERNAME']})",
        )
