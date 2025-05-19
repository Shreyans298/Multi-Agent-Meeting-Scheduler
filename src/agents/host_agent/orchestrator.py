# =============================================================================
# agents/host_agent/orchestrator.py
# =============================================================================
# 🎯 Purpose:
# Defines the OrchestratorAgent that coordinates between SchedulerAgent and CalendarAgent
# to handle meeting scheduling requests.
# =============================================================================

import os
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# -----------------------------------------------------------------------------
# FastAPI and Pydantic imports
# -----------------------------------------------------------------------------
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# -----------------------------------------------------------------------------
# A2A server-side infrastructure
# -----------------------------------------------------------------------------
from server.task_manager import InMemoryTaskManager
from models.request import SendTaskRequest, SendTaskResponse
from models.task import Message, TaskStatus, TaskState, TextPart

# -----------------------------------------------------------------------------
# Connector to child A2A agents
# -----------------------------------------------------------------------------
from agents.host_agent.agent_connect import AgentConnector
from models.agent import AgentCard

# Set up module-level logger
logger = logging.getLogger(__name__)

class MeetingRequest(BaseModel):
    """Model for meeting scheduling requests"""
    title: str
    description: Optional[str] = None
    duration_minutes: int
    participants: List[str]
    preferred_days: List[str]
    preferred_times: List[str]
    timezone: str

class MeetingResponse(BaseModel):
    """Model for meeting scheduling responses"""
    success: bool
    message: str
    meeting_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    updates: Optional[List[Dict[str, Any]]] = None

class OrchestratorAgent:
    """
    🤖 Coordinates between SchedulerAgent and CalendarAgent to handle meeting scheduling.
    """

    def __init__(self, agent_cards: list[AgentCard]):
        # Build connectors for SchedulerAgent and CalendarAgent
        self.connectors = {
            card.name: AgentConnector(card.name, card.url)
            for card in agent_cards
        }
        
        # Validate required agents are present
        required_agents = {"SchedulerAgent", "CalendarAgent"}
        missing_agents = required_agents - set(self.connectors.keys())
        if missing_agents:
            raise ValueError(f"Missing required agents: {missing_agents}")

        # Static user ID for session tracking
        self._user_id = "orchestrator_user"

    async def schedule_meeting(self, request: MeetingRequest) -> MeetingResponse:
        """
        Main entry point for scheduling meetings. Coordinates between:
        1. SchedulerAgent to find available time slots
        2. CalendarAgent to create the meeting
        """
        try:
            # Step 1: Get available time slots from SchedulerAgent
            scheduler_response = await self._get_available_slots(request)
            if not scheduler_response.get("success"):
                return MeetingResponse(
                    success=False,
                    message="Failed to find available time slots",
                    updates=[scheduler_response]
                )

            # Step 2: Create meeting using CalendarAgent
            calendar_response = await self._create_meeting(
                request,
                scheduler_response["start_time"],
                scheduler_response["end_time"]
            )

            return MeetingResponse(
                success=calendar_response.get("success", False),
                message=calendar_response.get("message", "Meeting creation failed"),
                meeting_id=calendar_response.get("meeting_id"),
                start_time=scheduler_response["start_time"],
                end_time=scheduler_response["end_time"],
                updates=[scheduler_response, calendar_response]
            )

        except Exception as e:
            logger.error(f"Error scheduling meeting: {str(e)}")
            return MeetingResponse(
                success=False,
                message=f"Error scheduling meeting: {str(e)}"
            )

    async def _get_available_slots(self, request: MeetingRequest) -> Dict[str, Any]:
        """Get available time slots from SchedulerAgent"""
        try:
            scheduler = self.connectors["SchedulerAgent"]
            response = await scheduler.send_task({
                "action": "find_slots",
                "participants": request.participants,
                "duration_minutes": request.duration_minutes,
                "preferred_days": request.preferred_days,
                "preferred_times": request.preferred_times,
                "timezone": request.timezone
            })
            
            return {
                "success": True,
                "agent": "SchedulerAgent",
                "start_time": response.get("start_time"),
                "end_time": response.get("end_time"),
                "message": "Found available time slot"
            }
        except Exception as e:
            logger.error(f"Error getting available slots: {str(e)}")
            return {
                "success": False,
                "agent": "SchedulerAgent",
                "message": f"Error finding available slots: {str(e)}"
            }

    async def _create_meeting(
        self,
        request: MeetingRequest,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """Create meeting using CalendarAgent"""
        try:
            calendar = self.connectors["CalendarAgent"]
            response = await calendar.send_task({
                "action": "create_meeting",
                "title": request.title,
                "description": request.description,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "participants": request.participants
            })
            
            return {
                "success": True,
                "agent": "CalendarAgent",
                "meeting_id": response.get("meeting_id"),
                "message": "Meeting created successfully"
            }
        except Exception as e:
            logger.error(f"Error creating meeting: {str(e)}")
            return {
                "success": False,
                "agent": "CalendarAgent",
                "message": f"Error creating meeting: {str(e)}"
            }

class OrchestratorTaskManager(InMemoryTaskManager):
    """Task manager for the OrchestratorAgent"""

    def __init__(self, agent: OrchestratorAgent):
        self.agent = agent

    def _get_meeting_request(self, request: SendTaskRequest) -> MeetingRequest:
        """Extract meeting request from task request"""
        try:
            return MeetingRequest(**request.message.parts[0].content)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid meeting request format: {str(e)}"
            )

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """Handle incoming task requests"""
        try:
            # Extract meeting request
            meeting_request = self._get_meeting_request(request)
            
            # Schedule meeting
            response = await self.agent.schedule_meeting(meeting_request)
            
            # Create task response
            return SendTaskResponse(
                task_id=str(uuid.uuid4()),
                status=TaskStatus.COMPLETED,
                state=TaskState.SUCCESS,
                message=Message(
                    role="assistant",
                    parts=[TextPart(text=response.json())]
                )
            )
        except Exception as e:
            logger.error(f"Error processing task: {str(e)}")
            return SendTaskResponse(
                task_id=str(uuid.uuid4()),
                status=TaskStatus.FAILED,
                state=TaskState.ERROR,
                message=Message(
                    role="assistant",
                    parts=[TextPart(text=f"Error: {str(e)}")]
                )
            )
