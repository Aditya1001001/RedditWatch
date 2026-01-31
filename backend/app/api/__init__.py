"""API routes for RedditWatch."""

from fastapi import APIRouter

from app.api import analysis, collect, export, insights, llm, posts, search, subreddits, themes

# Main API router
api_router = APIRouter(prefix="/api")

# Include all route modules
api_router.include_router(posts.router, prefix="/posts", tags=["posts"])
api_router.include_router(insights.router, prefix="/insights", tags=["insights"])
api_router.include_router(themes.router, prefix="/themes", tags=["themes"])
api_router.include_router(subreddits.router, prefix="/subreddits", tags=["subreddits"])
api_router.include_router(collect.router, prefix="/collect", tags=["collection"])
api_router.include_router(analysis.router, prefix="/analyze", tags=["analysis"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
api_router.include_router(llm.router, prefix="/llm", tags=["llm"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
