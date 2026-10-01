import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://commerce:commerce@localhost:5432/commerce"
    ).replace("postgresql://", "postgresql+psycopg://", 1)
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    jwt_secret: str = os.getenv("JWT_SECRET", "local-demo-secret-not-for-production")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    admin_email: str = os.getenv("ADMIN_EMAIL", "admin@example.com")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "LocalAdmin123!")


settings = Settings()
