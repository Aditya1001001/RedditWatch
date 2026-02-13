"""Scheduler management API endpoints."""

from fastapi import APIRouter, HTTPException

from app.services.scheduler import get_scheduler

router = APIRouter()


@router.get("/status")
async def get_scheduler_status():
    """Get scheduler status including all jobs and their next run times."""
    scheduler = get_scheduler()
    return scheduler.get_status()


@router.post("/start")
async def start_scheduler():
    """Start the collection scheduler."""
    scheduler = get_scheduler()
    if scheduler.running:
        return {"message": "Scheduler is already running", **scheduler.get_status()}
    scheduler.start()
    return {"message": "Scheduler started", **scheduler.get_status()}


@router.post("/stop")
async def stop_scheduler():
    """Stop the collection scheduler."""
    scheduler = get_scheduler()
    if not scheduler.running:
        return {"message": "Scheduler is not running", "running": False, "jobs": []}
    scheduler.stop()
    return {"message": "Scheduler stopped", "running": False, "jobs": []}


@router.post("/trigger/{job_id}")
async def trigger_job(job_id: str):
    """Manually trigger a specific scheduled job."""
    scheduler = get_scheduler()
    if not scheduler.running:
        raise HTTPException(
            status_code=400,
            detail="Scheduler is not running. Start it first via POST /api/scheduler/start",
        )
    if not scheduler.trigger_job(job_id):
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found. Available jobs: "
            + ", ".join(j["id"] for j in scheduler.get_job_summaries()),
        )
    return {"message": f"Job '{job_id}' triggered", **scheduler.get_status()}
