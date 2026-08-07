"""Application bootstrap for the sales data platform."""

import logging

from sales_data_platform.config.settings import Settings
from sales_data_platform.logging import configure_logging


def main() -> int:
    """Initialize application infrastructure and report successful startup."""
    settings = Settings()
    configure_logging(settings)
    logger = logging.getLogger(__name__)
    logger.info("Application started successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
