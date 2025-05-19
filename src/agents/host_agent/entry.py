# =============================================================================
# agents/host_agent/entry.py
# =============================================================================
# 🎯 Purpose:
# Boots up the OrchestratorAgent as an A2A server.
# Uses the shared registry file to discover all child agents,
# then delegates routing to the OrchestratorAgent via A2A JSON-RPC.
# =============================================================================

import click
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Union, Dict, Any
import httpx
from datetime import datetime
from enum import Enum
import base64

SCHEDULER_URL = "http://localhost:10001"
CALENDAR_URL = "http://localhost:10002"

app = FastAPI(title="HostAgent API")

class MessagePartType(str, Enum):
    TEXT = "text"
    DATA = "data"
    FILE = "file"

class MessagePart(BaseModel):
    type: MessagePartType
    content: Union[str, Dict[str, Any]]
    metadata: Optional[Dict[str, Any]] = None

class AgentUpdate(BaseModel):
    agent_id: str
    parts: List[MessagePart]
    timestamp: datetime = datetime.now()

class ScheduleMeetingRequest(BaseModel):
    title: str
    participants: List[str]
    description: str
    duration_minutes: int
    timezone: str
    updates: Optional[List[AgentUpdate]] = None

class ScheduleMeetingResponse(BaseModel):
    success: bool
    message: str
    meeting_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    updates: Optional[List[AgentUpdate]] = None

@app.post("/schedule-meeting", response_model=ScheduleMeetingResponse)
async def schedule_meeting(request: ScheduleMeetingRequest):
    updates = request.updates or []
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
            updates.append(AgentUpdate(
                agent_id="scheduler",
                parts=[MessagePart(
                    type=MessagePartType.TEXT,
                    content="Failed to find available time slot",
                    metadata={"error": scheduler_data.get("message")}
                )]
            ))
            return ScheduleMeetingResponse(
                success=False,
                message=scheduler_data.get("message", "No available time slot found."),
                updates=updates
            )

        updates.append(AgentUpdate(
            agent_id="scheduler",
            parts=[MessagePart(
                type=MessagePartType.DATA,
                content={
                    "start_time": scheduler_data["start_time"],
                    "end_time": scheduler_data["end_time"]
                }
            )]
        ))

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
            updates.append(AgentUpdate(
                agent_id="calendar",
                parts=[MessagePart(
                    type=MessagePartType.TEXT,
                    content="Failed to create meeting",
                    metadata={"error": calendar_data.get("message")}
                )]
            ))
            return ScheduleMeetingResponse(
                success=False,
                message=calendar_data.get("message", "Failed to create meeting."),
                updates=updates
            )

        updates.append(AgentUpdate(
            agent_id="calendar",
            parts=[MessagePart(
                type=MessagePartType.DATA,
                content={
                    "meeting_id": calendar_data.get("meeting_id"),
                    "status": "created"
                }
            )]
        ))

        return ScheduleMeetingResponse(
            success=True,
            message="Meeting scheduled successfully.",
            meeting_id=calendar_data.get("meeting_id"),
            start_time=scheduler_data["start_time"],
            end_time=scheduler_data["end_time"],
            updates=updates
        )

@app.post("/agent-update")
async def receive_agent_update(update: AgentUpdate):
    # Process the update based on its type
    for part in update.parts:
        if part.type == MessagePartType.TEXT:
            # Handle text updates
            print(f"Text update from {update.agent_id}: {part.content}")
        elif part.type == MessagePartType.DATA:
            # Handle data updates
            print(f"Data update from {update.agent_id}: {part.content}")
        elif part.type == MessagePartType.FILE:
            # Handle file updates
            print(f"File update from {update.agent_id}: {part.metadata}")
    
    return {"status": "received"}

@click.command()
@click.option('--host', default='localhost', help='Host to run the server on')
@click.option('--port', default=10000, help='Port to run the server on')
def main(host: str, port: int):
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()
