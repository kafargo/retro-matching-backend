"""Application configuration classes."""
import os


class Config:
    """Base configuration."""

    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///game.db")
    SQLALCHEMY_DATABASE_URI: str = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG: bool = True


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG: bool = False


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
