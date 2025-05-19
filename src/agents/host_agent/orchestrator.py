# =============================================================================
# agents/host_agent/orchestrator.py
# =============================================================================
# 🎯 Purpose:
# Defines the OrchestratorAgent that uses a Gemini-based LLM to interpret user
# queries and delegate them to any child A2A agent discovered at startup.
# Also defines OrchestratorTaskManager to expose this logic via JSON-RPC.
# =============================================================================

import os                           # Standard library for interacting with the operating system
import uuid                         # For generating unique identifiers (e.g., session IDs)
import logging                      # Standard library for configurable logging
from dotenv import load_dotenv      # Utility to load environment variables from a .env file

# Load the .env file so that environment variables like GOOGLE_API_KEY
# are available to the ADK client when creating LLMs
load_dotenv()

# -----------------------------------------------------------------------------
# Google ADK / Gemini imports
# -----------------------------------------------------------------------------
from google.adk.agents.llm_agent import LlmAgent
# LlmAgent: core class to define a Gemini-powered AI agent

from google.adk.sessions import InMemorySessionService
# InMemorySessionService: stores session state in memory (for simple demos)

from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
# InMemoryMemoryService: optional conversation memory stored in RAM

from google.adk.artifacts import InMemoryArtifactService
# InMemoryArtifactService: handles file/blob artifacts (unused here)

from google.adk.runners import Runner
# Runner: orchestrates agent, sessions, memory, and tool invocation

from google.adk.agents.readonly_context import ReadonlyContext
# ReadonlyContext: passed to system prompt function to read context

from google.adk.tools.tool_context import ToolContext
# ToolContext: passed to tool functions for state and actions

from google.genai import types           
# types.Content & types.Part: used to wrap user messages for the LLM

# -----------------------------------------------------------------------------
# A2A server-side infrastructure
# -----------------------------------------------------------------------------
from server.task_manager import InMemoryTaskManager
# InMemoryTaskManager: base class providing in-memory task storage and locking

from models.request import SendTaskRequest, SendTaskResponse
# Data models for incoming task requests and outgoing responses

from models.task import Message, TaskStatus, TaskState, TextPart
# Message: encapsulates role+parts; TaskStatus/State: status enums; TextPart: text payload

# -----------------------------------------------------------------------------
# Connector to child A2A agents
# -----------------------------------------------------------------------------
from agents.host_agent.agent_connect import AgentConnector
# AgentConnector: lightweight wrapper around A2AClient to call other agents

from models.agent import AgentCard
# AgentCard: metadata structure for agent discovery results

# Set up module-level logger for debug/info messages
logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """
    🤖 Uses a Gemini LLM to route incoming user queries,
    calling out to any discovered child A2A agents via tools.
    """

    # Define supported MIME types for input/output
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self, agent_cards: list[AgentCard]):
        # Build one AgentConnector per discovered AgentCard
        # agent_cards is a list of AgentCard objects returned by discovery
        self.connectors = {
            card.name: AgentConnector(card.name, card.url)
            for card in agent_cards
        }

        # Build the internal LLM agent with our custom tools and instructions
        self._agent = self._build_agent()

        # Static user ID for session tracking across calls
        self._user_id = "orchestrator_user"

        # Runner wires up sessions, memory, artifacts, and handles agent.run()
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    def _build_agent(self) -> LlmAgent:
        """
        Construct the Gemini-based LlmAgent with:
        - Model name
        - Agent name/description
        - System instruction callback
        - Available tool functions
        """
        return LlmAgent(
            model="gemini-1.5-flash-latest",    # Specify Gemini model version
            name="orchestrator_agent",          # Human identifier for this agent
            description="Delegates user queries to child A2A agents based on intent.",
            instruction=self._root_instruction,  # Function providing system prompt text
            tools=[
                self._list_agents,               # Tool 1: list available child agents
                self._delegate_task             # Tool 2: call a child agent
            ],
        )

    def _root_instruction(self, context: ReadonlyContext) -> str:
        """
        System prompt function: returns instruction text for the LLM,
        including which tools it can use and a list of child agents.
        """
        # Build a detailed description of each agent
        agent_descriptions = {
            "WeatherAgent": (
                "Use this agent for ANY questions about weather, including:\n"
                "- Current weather conditions\n"
                "- Temperature\n"
                "- Weather forecasts\n"
                "- Weather in specific locations\n"
                "Examples: 'What's the weather like in New York?', 'How's the temperature in London?', 'Tell me the weather in Tokyo'"
            ),
            "ClothingAgent": (
                "Use this agent for questions about what clothes to wear based on weather conditions.\n"
                "Examples: 'What should I wear in New York?', 'What clothes should I pack for London?', 'What's appropriate to wear in Tokyo?'"
            )
        }
        
        # Build a detailed list of agents and their purposes
        agent_list = "\n".join(
            f"- {name}:\n{desc}" 
            for name, desc in agent_descriptions.items() 
            if name in self.connectors
        )
        
        return (
            "You are an orchestrator that routes user queries to specialized agents. You have two tools:\n"
            "1) list_agents() -> list available child agents\n"
            "2) delegate_task(agent_name, message) -> call that agent\n\n"
            "Available agents and their purposes:\n" + agent_list + "\n\n"
            "IMPORTANT RULES:\n"
            "1. For ANY question about weather, temperature, or forecasts, ALWAYS use the WeatherAgent.\n"
            "2. For questions about what clothes to wear based on weather, use the ClothingAgent.\n"
            "3. If a question contains weather-related terms (weather, temperature, forecast, etc.), use the WeatherAgent.\n"
            "4. Do not make up responses or try to answer weather questions yourself.\n"
            "5. Always delegate weather-related queries to the WeatherAgent.\n"
            "6. If you're unsure, use the WeatherAgent for weather-related queries.\n\n"
            "Example routing:\n"
            "- 'What's the weather like?' -> WeatherAgent\n"
            "- 'How's the temperature?' -> WeatherAgent\n"
            "- 'Tell me about the weather' -> WeatherAgent\n"
            "- 'What should I wear?' -> ClothingAgent\n"
            "- 'What clothes do I need?' -> ClothingAgent"
        )

    def _list_agents(self) -> list[str]:
        """
        Tool function: returns the list of child-agent names currently registered.
        Called by the LLM when it wants to discover available agents.
        """
        return list(self.connectors.keys())

    async def _delegate_task(
        self,
        agent_name: str,
        message: str,
        tool_context: ToolContext
    ) -> str:
        """
        Tool function: forwards the `message` to the specified child agent
        (via its AgentConnector), waits for the response, and returns the
        text of the last reply.
        """
        try:
            # Validate agent_name exists
            if agent_name not in self.connectors:
                raise ValueError(f"Unknown agent: {agent_name}")
            connector = self.connectors[agent_name]

            # Ensure session_id persists across tool calls via tool_context.state
            state = tool_context.state
            if "session_id" not in state:
                state["session_id"] = str(uuid.uuid4())
            session_id = state["session_id"]

            # Log the delegation attempt
            logger.info(f"Delegating task to {agent_name}: {message}")

            # Delegate task asynchronously and await Task result
            child_task = await connector.send_task(message, session_id)

            # Extract text from the last history entry if available
            if child_task.history and len(child_task.history) > 1:
                response = child_task.history[-1].parts[0].text
                logger.info(f"Received response from {agent_name}: {response}")
                return response
            
            logger.warning(f"No response received from {agent_name}")
            return f"I apologize, but I couldn't get a response from the {agent_name}. Please try again."
        
        except Exception as e:
            logger.error(f"Error delegating task to {agent_name}: {str(e)}")
            return f"I apologize, but there was an error communicating with the {agent_name}. Please try again."

    def invoke(self, query: str, session_id: str) -> str:
        """
        Main entry: receives a user query + session_id,
        sets up or retrieves a session, wraps the query for the LLM,
        runs the Runner (with tools enabled), and returns the final text.
        """
        # Attempt to reuse an existing session
        session = self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id
        )
        # Create new if not found
        if session is None:
            session = self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                session_id=session_id,
                state={}
            )

        # Wrap the user query in a types.Content message
        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=query)]
        )

        # Run the agent synchronously; collects a list of events
        events = list(self._runner.run(
            user_id=self._user_id,
            session_id=session.id,
            new_message=content
        ))

        # If no content or parts, return empty fallback
        if not events or not events[-1].content or not events[-1].content.parts:
            return ""
        # Join all text parts into a single string reply
        return "\n".join(p.text for p in events[-1].content.parts if p.text)


class OrchestratorTaskManager(InMemoryTaskManager):
    """
    🪄 TaskManager wrapper: exposes OrchestratorAgent.invoke() over the
    A2A JSON-RPC `tasks/send` endpoint, handling in-memory storage and
    response formatting.
    """
    def __init__(self, agent: OrchestratorAgent):
        super().__init__()       # Initialize base in-memory storage
        self.agent = agent       # Store our orchestrator logic

    def _get_user_text(self, request: SendTaskRequest) -> str:
        """
        Helper: extract the user's raw input text from the request object.
        """
        return request.params.message.parts[0].text

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """
        Called by the A2A server when a new task arrives:
        1. Store the incoming user message
        2. Invoke the OrchestratorAgent to get a response
        3. Append response to history, mark completed
        4. Return a SendTaskResponse with the full Task
        """
        logger.info(f"OrchestratorTaskManager received task {request.params.id}")

        # Step 1: save the initial message
        task = await self.upsert_task(request.params)

        # Step 2: run orchestration logic
        user_text = self._get_user_text(request)
        response_text = self.agent.invoke(user_text, request.params.sessionId)

        # Step 3: wrap the LLM output into a Message
        reply = Message(role="agent", parts=[TextPart(text=response_text)])
        async with self.lock:
            task.status = TaskStatus(state=TaskState.COMPLETED)
            task.history.append(reply)

        # Step 4: return structured response
        return SendTaskResponse(id=request.id, result=task)
