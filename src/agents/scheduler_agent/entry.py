import click
import asyncio
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import pytz

from src.agents.scheduler_agent.scheduler_agent import SchedulerAgent

app = FastAPI(title="SchedulerAgent API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the SchedulerAgent
scheduler_agent = SchedulerAgent()

class ScheduleRequest(BaseModel):
    title: str
    participants: List[str]
    description: str
    duration_minutes: int
    timezone: str

class ScheduleResponse(BaseModel):
    success: bool
    message: str
    start_time: Optional[str] = None  # Changed to string to handle timezone serialization
    end_time: Optional[str] = None    # Changed to string to handle timezone serialization

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

@app.post("/schedule", response_model=ScheduleResponse)
async def schedule_meeting(request: ScheduleRequest):
    try:
        # Validate timezone
        try:
            pytz.timezone(request.timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            return ScheduleResponse(
                success=False,
                message=f"Invalid timezone: {request.timezone}"
            )

        # Find available time slot
        result = await scheduler_agent.find_next_available_time(
            participants=request.participants,
            duration_minutes=request.duration_minutes,
            timezone=request.timezone
        )
        
        if result["status"] != "success":
            error_message = result.get("message", "No available time slots found.")
            if not scheduler_agent.calendar_available:
                error_message += " (Calendar service is not available - using default scheduling)"
            return ScheduleResponse(
                success=False,
                message=error_message
            )
        
        try:
            # Parse the ISO format time and ensure it's in the correct timezone
            start_time = datetime.fromisoformat(result["available_time"])
            if start_time.tzinfo is None:
                start_time = pytz.timezone(request.timezone).localize(start_time)
            
            end_time = start_time + timedelta(minutes=request.duration_minutes)
            
            message = "Available time slot found"
            if not scheduler_agent.calendar_available:
                message += " (Calendar service is not available - using default scheduling)"
            
            return ScheduleResponse(
                success=True,
                message=message,
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat()
            )
        except ValueError as e:
            return ScheduleResponse(
                success=False,
                message=f"Error parsing time: {str(e)}"
            )
            
    except Exception as e:
        error_message = f"Error scheduling meeting: {str(e)}"
        if not scheduler_agent.calendar_available:
            error_message += " (Calendar service is not available)"
        return ScheduleResponse(
            success=False,
            message=error_message
        )

@click.command()
@click.option('--host', default='localhost', help='Host to run the server on')
@click.option('--port', default=10001, help='Port to run the server on')
def main(host: str, port: int):
    """Start the SchedulerAgent API server."""
    uvicorn.run(app, host=host, port=port)

if __name__ == '__main__':
    main() 