from typing import List, Dict
from datetime import datetime, timedelta
import pytz
import json
from .google_calendar_service import GoogleCalendarService

class CalendarAgent:
    def __init__(self, credentials_path: str = 'credentials.json', token_path: str = 'token.pickle'):
        self.timezone = pytz.UTC  # Default timezone
        try:
            self.calendar_service = GoogleCalendarService(credentials_path, token_path)
            self.calendar_available = True
        except Exception as e:
            print(f"Warning: Calendar service not available: {str(e)}")
            self.calendar_available = False

    async def handle_task(self, task_data: Dict) -> Dict:
        """
        Handle incoming A2A task requests.
        
        Args:
            task_data: Dictionary containing task parameters
            
        Returns:
            Dictionary containing task response
        """
        action = task_data.get('action')
        
        if action == 'create_meeting':
            return await self.create_meeting(
                title=task_data['title'],
                start_time=datetime.fromisoformat(task_data['start_time']),
                end_time=datetime.fromisoformat(task_data['end_time']),
                participants=task_data['participants'],
                description=task_data.get('description', ''),
                location=task_data.get('location', ''),
                timezone=task_data.get('timezone', 'UTC')
            )
        else:
            return {
                "status": "error",
                "message": f"Unknown action: {action}"
            }

    async def create_meeting(
        self,
        title: str,
        participants: List[str],
        description: str,
        start_time: datetime,
        end_time: datetime,
        timezone: str = "UTC"
    ) -> str:
        """
        Create a new meeting and send calendar invites.
        
        Args:
            title: Meeting title
            participants: List of participant email addresses
            description: Meeting description
            start_time: Meeting start time
            end_time: Meeting end time
            timezone: Timezone for the meeting
            
        Returns:
            Meeting ID
        """
        if not self.calendar_available:
            # Generate a mock meeting ID when calendar service is not available
            return f"mock_meeting_{datetime.now().timestamp()}"

        try:
            # Ensure timezone is set
            if not start_time.tzinfo:
                start_time = pytz.timezone(timezone).localize(start_time)
            if not end_time.tzinfo:
                end_time = pytz.timezone(timezone).localize(end_time)

            event = self.calendar_service.create_event(
                summary=title,
                start_time=start_time,
                end_time=end_time,
                attendees=participants,
                description=description
            )
            return event['id']
        except FileNotFoundError as e:
            print(f"Calendar credentials not found: {str(e)}")
            self.calendar_available = False
            return f"mock_meeting_{datetime.now().timestamp()}"
        except Exception as e:
            print(f"Error creating meeting: {str(e)}")
            # Return a mock meeting ID in case of error
            return f"mock_meeting_{datetime.now().timestamp()}"

    def send_reminder(
        self,
        meeting_id: str,
        reminder_minutes: int = 15
    ) -> bool:
        """
        Send a reminder for an upcoming meeting.
        
        Args:
            meeting_id: ID of the meeting
            reminder_minutes: Minutes before the meeting to send the reminder
            
        Returns:
            True if reminder was sent successfully
        """
        try:
            self.calendar_service.update_event(
                meeting_id,
                {
                    'reminders': {
                        'useDefault': False,
                        'overrides': [
                            {'method': 'email', 'minutes': reminder_minutes},
                            {'method': 'popup', 'minutes': reminder_minutes},
                        ],
                    }
                }
            )
            return True
        except Exception:
            return False

    def update_meeting(
        self,
        meeting_id: str,
        updates: Dict
    ) -> bool:
        """
        Update meeting details and notify participants.
        
        Args:
            meeting_id: ID of the meeting
            updates: Dictionary containing updated meeting details
            
        Returns:
            True if update was successful
        """
        try:
            self.calendar_service.update_event(meeting_id, updates)
            return True
        except Exception:
            return False

    def cancel_meeting(
        self,
        meeting_id: str,
        notify_participants: bool = True
    ) -> bool:
        """
        Cancel a meeting and notify participants.
        
        Args:
            meeting_id: ID of the meeting
            notify_participants: Whether to notify participants of cancellation
            
        Returns:
            True if cancellation was successful
        """
        return self.calendar_service.delete_event(
            meeting_id,
            send_updates=notify_participants
        )

    def create_recurring_meeting(
        self,
        title: str,
        start_time: datetime,
        duration_minutes: int,
        participants: List[str],
        preferred_days: List[str],
        preferred_hours: Dict[str, List[int]],
        description: str = "",
        location: str = "",
        timezone: str = "UTC",
        weeks: int = 4
    ) -> Dict:
        """
        Create a recurring meeting based on preferred days and times.
        
        Args:
            title: Meeting title
            start_time: Initial meeting start time
            duration_minutes: Duration of the meeting in minutes
            participants: List of participant email addresses
            preferred_days: List of preferred days (e.g., ["Monday", "Tuesday"])
            preferred_hours: Dictionary of preferred hours for each day
            description: Meeting description
            location: Meeting location (physical or virtual)
            timezone: Timezone for the meeting
            weeks: Number of weeks to schedule the recurring meeting
            
        Returns:
            Dictionary containing meeting details and status
        """
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        event = self.calendar_service.create_recurring_event(
            summary=title,
            start_time=start_time,
            end_time=end_time,
            attendees=participants,
            preferred_days=preferred_days,
            preferred_hours=preferred_hours,
            description=description,
            location=location,
            weeks=weeks
        )
        
        return {
            "status": "success",
            "meeting_id": event['id'],
            "calendar_link": event['htmlLink'],
            "recurrence": event.get('recurrence', [])
        } 