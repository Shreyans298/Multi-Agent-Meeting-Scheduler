from typing import List, Dict, Optional
from datetime import datetime, timedelta
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import pytz

class GoogleCalendarService:
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    
    def __init__(self, credentials_path: str = 'credentials.json', token_path: str = 'token.pickle'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self.credentials = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Google Calendar API."""
        try:
            if os.path.exists(self.token_path):
                with open(self.token_path, 'rb') as token:
                    self.credentials = pickle.load(token)

            if not self.credentials or not self.credentials.valid:
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    self.credentials.refresh(Request())
                else:
                    if not os.path.exists(self.credentials_path):
                        raise FileNotFoundError(f"Credentials file not found: {self.credentials_path}")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, self.SCOPES)
                    self.credentials = flow.run_local_server(port=0)

                with open(self.token_path, 'wb') as token:
                    pickle.dump(self.credentials, token)

            self.service = build('calendar', 'v3', credentials=self.credentials)
        except Exception as e:
            print(f"Authentication error: {str(e)}")
            raise

    def get_events(
        self,
        time_min: datetime,
        time_max: datetime,
        calendar_id: str = 'primary'
    ) -> List[Dict]:
        """Get events from calendar within the specified time range."""
        time_min = time_min.isoformat() + 'Z'
        time_max = time_max.isoformat() + 'Z'
        
        events_result = self.service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        return events_result.get('items', [])

    def create_event(
        self,
        summary: str,
        start_time: datetime,
        end_time: datetime,
        attendees: List[str],
        description: str = "",
        location: str = "",
        calendar_id: str = 'primary'
    ) -> Dict:
        """Create a new calendar event."""
        try:
            # Ensure timezone is set
            if not start_time.tzinfo:
                start_time = pytz.UTC.localize(start_time)
            if not end_time.tzinfo:
                end_time = pytz.UTC.localize(end_time)

            event = {
                'summary': summary,
                'location': location,
                'description': description,
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': str(start_time.tzinfo),
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': str(end_time.tzinfo),
                },
                'attendees': [{'email': email} for email in attendees],
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},
                        {'method': 'popup', 'minutes': 30},
                    ],
                },
            }

            if not self.service:
                raise Exception("Calendar service not initialized")

            event = self.service.events().insert(
                calendarId=calendar_id,
                body=event,
                sendUpdates='all'
            ).execute()
            
            return event
        except Exception as e:
            print(f"Error creating event: {str(e)}")
            raise

    def update_event(
        self,
        event_id: str,
        updates: Dict,
        calendar_id: str = 'primary'
    ) -> Dict:
        """Update an existing calendar event."""
        event = self.service.events().get(
            calendarId=calendar_id,
            eventId=event_id
        ).execute()

        # Update event with new details
        for key, value in updates.items():
            event[key] = value

        updated_event = self.service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event,
            sendUpdates='all'
        ).execute()
        
        return updated_event

    def delete_event(
        self,
        event_id: str,
        calendar_id: str = 'primary',
        send_updates: bool = True
    ) -> bool:
        """Delete a calendar event."""
        try:
            self.service.events().delete(
                calendarId=calendar_id,
                eventId=event_id,
                sendUpdates='all' if send_updates else 'none'
            ).execute()
            return True
        except Exception:
            return False

    def get_free_busy(
        self,
        time_min: datetime,
        time_max: datetime,
        attendees: List[str]
    ) -> Dict:
        """Get free/busy information for attendees."""
        body = {
            'timeMin': time_min.isoformat(),
            'timeMax': time_max.isoformat(),
            'items': [{'id': email} for email in attendees]
        }
        
        events_result = self.service.freebusy().query(body=body).execute()
        return events_result.get('calendars', {})

    def create_recurring_event(
        self,
        summary: str,
        start_time: datetime,
        end_time: datetime,
        attendees: List[str],
        preferred_days: List[str],
        preferred_hours: Dict[str, List[int]],
        description: str = "",
        location: str = "",
        calendar_id: str = 'primary',
        weeks: int = 4  # Number of weeks to schedule
    ) -> Dict:
        """Create recurring calendar events by creating individual events for each day."""
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
        
        # Get the base date (next occurrence of the first preferred day)
        base_date = start_time.date()
        days_ahead = day_to_number[preferred_days[0]] - base_date.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        base_date = base_date + timedelta(days=days_ahead)
        
        # Create events for each week
        created_events = []
        for week in range(weeks):
            for day in preferred_days:
                # Calculate the date for this day
                days_ahead = day_to_number[day] - base_date.weekday()
                if days_ahead < 0:
                    days_ahead += 7
                event_date = base_date + timedelta(days=days_ahead + (week * 7))
                
                # Create the event for this day
                event_start = datetime.combine(event_date, start_time.time())
                event_end = datetime.combine(event_date, end_time.time())
                
                # Ensure timezone is properly set
                if start_time.tzinfo:
                    event_start = start_time.tzinfo.localize(event_start)
                    event_end = start_time.tzinfo.localize(event_end)
                
                event = {
                    'summary': summary,
                    'location': location,
                    'description': description,
                    'start': {
                        'dateTime': event_start.isoformat(),
                        'timeZone': str(start_time.tzinfo) if start_time.tzinfo else 'UTC',
                    },
                    'end': {
                        'dateTime': event_end.isoformat(),
                        'timeZone': str(end_time.tzinfo) if end_time.tzinfo else 'UTC',
                    },
                    'attendees': [{'email': email} for email in attendees],
                    'reminders': {
                        'useDefault': False,
                        'overrides': [
                            {'method': 'email', 'minutes': 24 * 60},
                            {'method': 'popup', 'minutes': 30},
                        ],
                    }
                }
                
                try:
                    created_event = self.service.events().insert(
                        calendarId=calendar_id,
                        body=event,
                        sendUpdates='all'
                    ).execute()
                    created_events.append(created_event)
                except Exception as e:
                    print(f"Error creating event for {day}: {str(e)}")
                    print(f"Event data: {event}")
                    raise
        
        # Return the first event as the main event
        return created_events[0] if created_events else None 