import click
import asyncio
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import pytz

from src.agents.calendar_agent.calendar_agent import CalendarAgent

app = FastAPI(title="CalendarAgent API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the CalendarAgent
calendar_agent = CalendarAgent()

class CreateMeetingRequest(BaseModel):
    title: str
    participants: List[str]
    description: str
    start_time: datetime
    end_time: datetime
    timezone: str

class CreateMeetingResponse(BaseModel):
    success: bool
    message: str
    meeting_id: Optional[str] = None

@app.post("/create-meeting", response_model=CreateMeetingResponse)
async def create_meeting(request: CreateMeetingRequest):
    try:
        # Validate timezone
        try:
            pytz.timezone(request.timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            return CreateMeetingResponse(
                success=False,
                message=f"Invalid timezone: {request.timezone}"
            )

        # Create the meeting
        meeting_id = await calendar_agent.create_meeting(
            title=request.title,
            participants=request.participants,
            description=request.description,
            start_time=request.start_time,
            end_time=request.end_time,
            timezone=request.timezone
        )
        
        message = "Meeting created successfully"
        if not calendar_agent.calendar_available:
            message += " (Calendar service is not available - using mock meeting ID)"
        
        return CreateMeetingResponse(
            success=True,
            message=message,
            meeting_id=meeting_id
        )
    except Exception as e:
        error_message = f"Error creating meeting: {str(e)}"
        if not calendar_agent.calendar_available:
            error_message += " (Calendar service is not available)"
        return CreateMeetingResponse(
            success=False,
            message=error_message
        )

@click.command()
@click.option('--host', default='localhost', help='Host to run the server on')
@click.option('--port', default=10002, help='Port to run the server on')
def main(host: str, port: int):
    """Start the CalendarAgent API server."""
    uvicorn.run(app, host=host, port=port)

if __name__ == '__main__':
    main() 