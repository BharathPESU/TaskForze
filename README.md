# NEXUS

> The AI assistant that will not let you forget.

Nexus is a proactive multi-agent workflow layer built around FastAPI, Gemini, semantic memory, and a live graph dashboard. It coordinates five specialist agents across calendar, tasks, notes, comms, and reminders, then escalates overdue work through WhatsApp Cloud and Vapi voice calls.

## Architecture

- Backend: FastAPI + APScheduler + structured workflow trace
- Agents: orchestrator, calendar, task, notes, comms, reminder
- Memory: semantic note retrieval plus shared in-memory workflow state
- Tasks: SQLAlchemy models plus a DAG-based ranking engine
- Frontend: React dashboard with live agent graph, task queue, and trace panel
- Escalation: Meta WhatsApp Cloud API first, Vapi voice second

## Run locally

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
uvicorn nexus.main:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend
npm run dev
```

The Vite app runs on `http://localhost:3000` and proxies API traffic to the FastAPI backend on `http://localhost:8000`.

## Key flows

1. `POST /chat` streams trace events and a final result for a workflow request.
2. `GET /agents/status` returns the live graph state for all agents.
3. `GET /tasks` returns ranked actionable tasks with dependency-aware priority scores.
4. `POST /webhook/whatsapp` handles inbound text and button replies from Meta Cloud API.
5. `POST /webhook/vapi` handles voice escalation outcomes.

## Project structure

```text
NEXUS/
├── nexus/
│   ├── agents/
│   │   ├── orchestrator.py
│   │   ├── calendar_agent.py
│   │   ├── task_agent.py
│   │   ├── notes_agent.py
│   │   ├── comms_agent.py
│   │   ├── reminder_agent.py
│   │   ├── runner.py
│   │   └── runtime.py
│   ├── db/
│   │   ├── engine.py
│   │   ├── models.py
│   │   └── schema.py
│   ├── memory/
│   │   ├── semantic_memory.py
│   │   └── workflow_state.py
│   ├── middleware/
│   │   └── security.py
│   ├── routers/
│   │   ├── chat.py
│   │   ├── webhooks.py
│   │   └── workflows.py
│   ├── scheduler/
│   │   └── reminder_scheduler.py
│   ├── tools/
│   │   ├── calendar_tools.py
│   │   ├── db_tools.py
│   │   ├── dependency_graph.py
│   │   ├── email_scanner.py
│   │   ├── gemini_tools.py
│   │   ├── gmail_tools.py
│   │   ├── mcp_tools.py
│   │   ├── retry.py
│   │   ├── vapi_tools.py
│   │   └── whatsapp_tools.py
│   ├── config.py
│   └── main.py
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── AgentGraph.jsx
│       ├── TracePanel.jsx
│       ├── index.css
│       └── main.jsx
├── .env.example
├── Dockerfile
└── requirements.txt
```

## Environment

See [.env.example](/home/balaraj/google%20apac/NEXUS/.env.example) for the full variable list. The most important groups are:

- Gemini: `GOOGLE_API_KEY`, `GEMINI_MODEL`
- Database: `DATABASE_URL`
- WhatsApp Cloud: `WHATSAPP_PHONE_ID`, `WHATSAPP_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `USER_WHATSAPP_NUMBER`
- Vapi: `VAPI_API_KEY`, `VAPI_WEBHOOK_URL`, `VAPI_WEBHOOK_SECRET`
- MCP: `GCAL_MCP_URL`, `GCAL_MCP_TOKEN`, `GMAIL_MCP_URL`, `GMAIL_MCP_TOKEN`
- App: `FRONTEND_URL`, `WEBHOOK_BASE_URL`, `USER_NAME`

## Verification

The current repo has been verified with:

- `python3 -m compileall nexus`
- `npm run build`
- An end-to-end orchestrator smoke test against temporary SQLite
- A SQLite schema compatibility test for older local workflow tables
