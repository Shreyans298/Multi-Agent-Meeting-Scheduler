import click
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import httpx
from datetime import datetime
import asyncio

SCHEDULER_URL = "http://localhost:10001"
CALENDAR_URL = "http://localhost:10002"
HOST_AGENT_URL = "http://localhost:10000"

app = FastAPI(title="HostAgent API")

class ScheduleMeetingRequest(BaseModel):
    title: str
    participants: List[str]
    description: str
    duration_minutes: int
    timezone: str

class ScheduleMeetingResponse(BaseModel):
    success: bool
    message: str
    meeting_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

@app.post("/schedule-meeting", response_model=ScheduleMeetingResponse)
async def schedule_meeting(request: ScheduleMeetingRequest):
    async with httpx.AsyncClient() as client:
        # 1. Ask SchedulerAgent for available slot
        scheduler_resp = await client.post(
            f"{SCHEDULER_URL}/schedule",
            json={
                "title": request.title,
                "participants": request.participants,
                "description": request.description,
                "duration_minutes": request.duration_minutes,
                "timezone": request.timezone
            }
        )
        scheduler_data = scheduler_resp.json()
        if scheduler_resp.status_code != 200 or not scheduler_data.get("success"):
            return ScheduleMeetingResponse(
                success=False,
                message=scheduler_data.get("message", "No available time slot found.")
            )
        # 2. Ask CalendarAgent to create the meeting
        calendar_resp = await client.post(
            f"{CALENDAR_URL}/create-meeting",
            json={
                "title": request.title,
                "participants": request.participants,
                "description": request.description,
                "start_time": scheduler_data["start_time"],
                "end_time": scheduler_data["end_time"],
                "timezone": request.timezone
            }
        )
        calendar_data = calendar_resp.json()
        if calendar_resp.status_code != 200 or not calendar_data.get("success"):
            return ScheduleMeetingResponse(
                success=False,
                message=calendar_data.get("message", "Failed to create meeting.")
            )
        return ScheduleMeetingResponse(
            success=True,
            message="Meeting scheduled successfully.",
            meeting_id=calendar_data.get("meeting_id"),
            start_time=scheduler_data["start_time"],
            end_time=scheduler_data["end_time"]
        )

@click.command()
@click.option('--title', prompt='Meeting title', help='Title of the meeting')
@click.option('--participants', prompt='Participant emails (comma-separated)', help='List of participant email addresses')
@click.option('--description', prompt='Meeting description', help='Description of the meeting')
@click.option('--duration', prompt='Duration in minutes', type=int, help='Duration of the meeting in minutes')
@click.option('--timezone', default='UTC', help='Timezone for the meeting')
def schedule_meeting(title, participants, description, duration, timezone):
    """Schedule a meeting with the given participants using HostAgent."""
    participant_list = [email.strip() for email in participants.split(',')]
    
    async def run():
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{HOST_AGENT_URL}/schedule-meeting",
                json={
                    "title": title,
                    "participants": participant_list,
                    "description": description,
        "duration_minutes": duration,
        "timezone": timezone
    }
            )
            if response.status_code != 200:
                click.echo(f"Error: {response.text}")
                return
            data = response.json()
            if data["success"]:
                click.echo(f"Meeting scheduled successfully!")
                click.echo(f"Start time: {data['start_time']}")
                click.echo(f"End time: {data['end_time']}")
                click.echo(f"Meeting ID: {data['meeting_id']}")
            else:
                click.echo(f"Failed to schedule meeting: {data.get('message', 'Unknown error')}")
    asyncio.run(run())

if __name__ == '__main__':
    schedule_meeting() 