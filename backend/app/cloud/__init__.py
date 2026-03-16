"""RedditWatch Cloud (SaaS-only) modules.

This package is excluded from the open-source distribution.
Modules here are loaded only when EDITION=cloud.
"""

import logging

logger = logging.getLogger(__name__)


def register_cloud_routes(app):
    """Register cloud-only API routes on the FastAPI app."""
    from app.cloud.auth import router as auth_router
    from app.cloud.billing import router as billing_router

    app.include_router(auth_router, prefix="/api/cloud")
    app.include_router(billing_router, prefix="/api/cloud")
    logger.info("Cloud routes registered")
