from typing import List, Dict, Optional
from datetime import datetime, timedelta
import pytz
import json
from ..calendar_agent.google_calendar_service import GoogleCalendarService

class SchedulerAgent:
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
        
        if action == 'find_available_time':
            return await self.find_next_available_time(
                participants=task_data['participants'],
                duration_minutes=task_data['duration_minutes'],
                timezone=task_data.get('timezone', 'UTC')
            )
        else:
            return {
                "status": "error",
                "message": f"Unknown action: {action}"
            }

    def _check_availability(
        self,
        participants: List[str],
        start_time: datetime,
        end_time: datetime
    ) -> bool:
        """
        Check if all participants are available during the given time slot.
        
        Args:
            participants: List of participant email addresses
            start_time: Start time of the slot
            end_time: End time of the slot
            
        Returns:
            True if all participants are available, False otherwise
        """
        if not self.calendar_available:
            # If calendar service is not available, assume the time slot is available
            return True
            
        try:
            free_busy = self.calendar_service.get_free_busy(
                time_min=start_time,
                time_max=end_time,
                attendees=participants
            )
            
            for participant in participants:
                if participant in free_busy:
                    busy_slots = free_busy[participant].get('busy', [])
                    for slot in busy_slots:
                        slot_start = datetime.fromisoformat(slot['start'].replace('Z', '+00:00'))
                        slot_end = datetime.fromisoformat(slot['end'].replace('Z', '+00:00'))
                        
                        if (start_time < slot_end and end_time > slot_start):
                            return False
            
            return True
        except Exception as e:
            print(f"Warning: Error checking availability: {str(e)}")
            # If there's an error checking availability, assume the time slot is available
            return True

    async def find_next_available_time(
        self,
        participants: List[str],
        duration_minutes: int,
        timezone: str = 'UTC'
    ) -> Dict:
        """
        Find the next available time slot for all participants.
        
        Args:
            participants: List of participant email addresses
            duration_minutes: Duration of the meeting in minutes
            timezone: Timezone for the meeting
            
        Returns:
            Dictionary containing the next available time or error
        """
        try:
            tz = pytz.timezone(timezone)
            current_time = datetime.now(tz)
            
            # Look ahead for 7 days, checking every 30 minutes
            end_time = current_time + timedelta(days=7)
            
            while current_time < end_time:
                # Skip non-business hours (9 AM to 5 PM)
                if current_time.hour < 9 or current_time.hour >= 17:
                    current_time += timedelta(minutes=30)
                    continue
                    
                # Skip weekends
                if current_time.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
                    current_time += timedelta(days=1)
                    current_time = current_time.replace(hour=9, minute=0, second=0, microsecond=0)
                    continue
                
                end_time_slot = current_time + timedelta(minutes=duration_minutes)
                
                if self._check_availability(participants, current_time, end_time_slot):
                    return {
                        "status": "success",
                        "available_time": current_time.isoformat(),
                        "timezone": timezone
                    }
                
                current_time += timedelta(minutes=30)
            
            return {
                "status": "error",
                "message": "No available time slots found in the next 7 days"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error finding available time: {str(e)}"
            }

    def find_optimal_meeting_time(
        self,
        participants: List[str],
        duration_minutes: int,
        preferred_days: List[str],
        preferred_hours: Dict[str, List[int]],
        timezone: str = 'UTC'
    ) -> Optional[datetime]:
        """
        Find optimal meeting times for each preferred day based on participant availability.
        
        Args:
            participants: List of participant email addresses
            duration_minutes: Duration of the meeting in minutes
            preferred_days: List of preferred days (e.g., ["Monday", "Tuesday"])
            preferred_hours: Dictionary mapping days to lists of preferred hours
            timezone: Timezone for the meeting
            
        Returns:
            Dictionary mapping days to optimal meeting times, or None if no suitable times found
        """
        tz = pytz.timezone(timezone)
        current_date = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Convert day names to numbers (0 = Monday, 6 = Sunday)
        day_to_number = {
            'Monday': 0,
            'Tuesday': 1,
            'Wednesday': 2,
            'Thursday': 3,
            'Friday': 4,
            'Saturday': 5,
            'Sunday': 6
        }
        
        optimal_times = {}
        
        # Check each preferred day
        for day in preferred_days:
            # Find the next occurrence of this day
            days_ahead = day_to_number[day] - current_date.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            target_date = current_date + timedelta(days=days_ahead)
            
            # Get the preferred hours for this day
            day_hours = preferred_hours.get(day, [])
            if not day_hours:
                continue
                
            # Check each hour in the preferred hours
            for hour in day_hours:
                start_time = target_date.replace(hour=hour, minute=0)
                end_time = start_time + timedelta(minutes=duration_minutes)
                
                # Check if all participants are available
                if self._check_availability(participants, start_time, end_time):
                    optimal_times[day] = start_time
                    break  # Found optimal time for this day
        
        return optimal_times if optimal_times else None

    def get_participant_availability(
        self,
        participant: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, datetime]]:
        """
        Get a participant's availability for a given date range.
        
        Args:
            participant: Participant's email address
            start_date: Start date for availability check
            end_date: End date for availability check
            
        Returns:
            List of available time slots
        """
        free_busy = self.calendar_service.get_free_busy(
            time_min=start_date,
            time_max=end_date,
            attendees=[participant]
        )
        
        if participant not in free_busy:
            return []
        
        busy_slots = free_busy[participant].get('busy', [])
        available_slots = []
        
        current_time = start_date
        for slot in busy_slots:
            slot_start = datetime.fromisoformat(slot['start'].replace('Z', '+00:00'))
            slot_end = datetime.fromisoformat(slot['end'].replace('Z', '+00:00'))
            
            if current_time < slot_start:
                available_slots.append({
                    'start': current_time,
                    'end': slot_start
                })
            
            current_time = slot_end
        
        if current_time < end_date:
            available_slots.append({
                'start': current_time,
                'end': end_date
            })
        
        return available_slots

    def suggest_alternative_times(
        self,
        original_time: datetime,
        participants: List[str],
        duration_minutes: int
    ) -> List[datetime]:
        """
        Suggest alternative meeting times if the original time doesn't work.
        
        Args:
            original_time: Original proposed meeting time
            participants: List of participant email addresses
            duration_minutes: Duration of the meeting in minutes
            
        Returns:
            List of alternative meeting times
        """
        # Look for alternatives within 2 hours before and after the original time
        start_date = original_time - timedelta(hours=2)
        end_date = original_time + timedelta(hours=2)
        
        free_busy = self.calendar_service.get_free_busy(
            time_min=start_date,
            time_max=end_date,
            attendees=participants
        )
        
        alternative_times = []
        current_time = start_date
        
        while current_time < end_date:
            end_time = current_time + timedelta(minutes=duration_minutes)
            
            # Check if all participants are available
            is_available = True
            for participant in participants:
                if participant in free_busy:
                    busy_slots = free_busy[participant].get('busy', [])
                    for slot in busy_slots:
                        slot_start = datetime.fromisoformat(slot['start'].replace('Z', '+00:00'))
                        slot_end = datetime.fromisoformat(slot['end'].replace('Z', '+00:00'))
                        
                        if (current_time < slot_end and end_time > slot_start):
                            is_available = False
                            break
                
                if not is_available:
                    break
            
            if is_available:
                alternative_times.append(current_time)
            
            # Move to next 30-minute slot
            current_time += timedelta(minutes=30)
        
        return alternative_times 

    async def find_available_time_slot(self, participants: List[str], duration_minutes: int, timezone: str) -> Optional[datetime]:
        # Logic to find an available time slot
        # For example, check participant calendars and return the next available time
        # This is a placeholder - replace with actual logic
        return datetime.now()  # Replace with actual logic 