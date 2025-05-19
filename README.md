# Event Scheduler Multi-Agent System

A robust multi-agent system for scheduling meetings using the A2A (Agent-to-Agent) protocol. This system implements a distributed architecture where specialized agents work together to handle meeting scheduling requests.

## Architecture

The system consists of three main agents:

1. **Host Agent**: The central orchestrator that receives scheduling requests and coordinates between other agents.
2. **Scheduler Agent**: Responsible for finding available time slots based on participants' calendars.
3. **Calendar Agent**: Handles the actual creation and management of calendar events.

### Communication Flow

```
Client -> Host Agent -> Scheduler Agent -> Calendar Agent
```

## Features

- Dynamic message handling with support for multiple message types
- Robust error handling and fallback mechanisms
- Timezone-aware scheduling
- Google Calendar integration (with fallback to mock mode)
- FastAPI-based REST endpoints for agent communication

## Prerequisites

- Python 3.9 or higher
- Google Calendar API credentials

## Installation

1. Clone the repository:
```bash
git clone https://github.com/Shreyans298/Multi-Agent-Meeting-Scheduler.git
cd event_scheduler_multi-agent
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -e .
```

## Configuration

1. For Google Calendar integration, place your `credentials.json` file in the project root directory.
2. The first time you run the application with Google Calendar integration, it will prompt you to authenticate.

## Usage

1. Start the application:
```bash
python src/main.py
```

2. The system will start three agents:
   - Host Agent: http://localhost:8000
   - Scheduler Agent: http://localhost:8001
   - Calendar Agent: http://localhost:8002

3. Send a meeting request to the Host Agent:
```bash
curl -X POST http://localhost:8000/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Team Meeting",
    "description": "Weekly sync",
    "duration_minutes": 60,
    "participants": ["user1@example.com", "user2@example.com"],
    "preferred_days": ["Monday", "Wednesday", "Friday"],
    "preferred_times": ["09:00", "14:00", "16:00"],
    "timezone": "UTC"
  }'
```

## Project Structure

```
event_scheduler_multi-agent/
├── src/
│   ├── agents/
│   │   ├── host_agent/
│   │   ├── scheduler_agent/
│   │   └── calendar_agent/
│   ├── models/
│   │   ├── agent.py
│   │   └── request.py
│   ├── main.py
│   └── config.py
├── requirements.txt
├── pyproject.toml
└── setup.py
```

## Error Handling

The system implements robust error handling:
- Graceful degradation when Google Calendar service is unavailable
- Fallback to mock mode for testing and development
- Detailed error messages for debugging

## Development

### Adding New Message Types

1. Define new message types in the appropriate agent's models
2. Update the message handling logic in the agent's entry point
3. Implement the corresponding business logic

### Testing

Run the test suite:
```bash
pytest
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## Authors

- Shreyans Jain (jain.shreyans03@gmail.com)

## Acknowledgments

- FastAPI for the web framework
- Google Calendar API for calendar integration
- Pydantic for data validation 