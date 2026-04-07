import { useEffect, useMemo, useRef, useState } from 'react'
import AgentGraph from './AgentGraph'
import TracePanel from './TracePanel'

const QUICK_ACTIONS = [
  'Set me up for the week',
  "What's my day?",
  'Add task: review contract by Friday',
  'Draft an update email for the team',
  'Search notes for demo prep',
]

const EMPTY_AGENTS = [
  { name: 'orchestrator', status: 'idle', message: 'Waiting for work', type: 'primary' },
  { name: 'calendar', status: 'idle', message: 'Watching time', type: 'sub-agent' },
  { name: 'task', status: 'idle', message: 'Ranking work', type: 'sub-agent' },
  { name: 'notes', status: 'idle', message: 'Holding context', type: 'sub-agent' },
  { name: 'comms', status: 'idle', message: 'Ready to draft', type: 'sub-agent' },
  { name: 'reminder', status: 'idle', message: 'Polling deadlines', type: 'autonomous' },
]

function formatDate(value) {
  if (!value) return 'No deadline'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('en-IN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatTime(value) {
  if (!value) return '--:--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function parseEventBlock(block) {
  if (!block.trim()) return null
  const lines = block.split('\n')
  let eventType = 'message'
  let data = ''
  for (const line of lines) {
    if (line.startsWith('event:')) eventType = line.slice(6).trim()
    if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  if (!data) return null
  try {
    return { eventType, payload: JSON.parse(data) }
  } catch {
    return null
  }
}

export default function App() {
  const [input, setInput] = useState('')
  const [trace, setTrace] = useState([])
  const [agents, setAgents] = useState(EMPTY_AGENTS)
  const [tasks, setTasks] = useState([])
  const [workflows, setWorkflows] = useState([])
  const [summary, setSummary] = useState('')
  const [warnings, setWarnings] = useState([])
  const [keyActions, setKeyActions] = useState([])
  const [suggestions, setSuggestions] = useState([])
  const [workflowId, setWorkflowId] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [auth, setAuth] = useState(null)
  const [banner, setBanner] = useState('')
  const traceRef = useRef(null)

  useEffect(() => {
    loadDashboard()
    const interval = window.setInterval(loadDashboard, 10000)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const authState = params.get('auth')
    if (!authState) return
    if (authState === 'success') setBanner('Google account connected.')
    if (authState === 'error') setBanner(`Authentication failed: ${params.get('message') || 'unknown error'}`)
    if (authState === 'already_connected') setBanner('Google account already connected.')
    if (authState === 'needs_setup') {
      setBanner('Add Google OAuth client credentials first, then try Connect Google again.')
    }
    window.history.replaceState({}, '', '/')
  }, [])

  useEffect(() => {
    traceRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [trace])

  async function loadDashboard() {
    const requests = await Promise.allSettled([
      fetch('/agents/status').then((res) => res.json()),
      fetch('/tasks').then((res) => res.json()),
      fetch('/workflows').then((res) => res.json()),
      fetch('/auth/status').then((res) => res.json()),
    ])

    if (requests[0].status === 'fulfilled') {
      setAgents(normalizeAgents(requests[0].value.agents || []))
    }
    if (requests[1].status === 'fulfilled') {
      setTasks(Array.isArray(requests[1].value) ? requests[1].value : [])
    }
    if (requests[2].status === 'fulfilled') {
      setWorkflows(Array.isArray(requests[2].value) ? requests[2].value : [])
    }
    if (requests[3].status === 'fulfilled') {
      setAuth(requests[3].value)
    }
  }

  async function handleSubmit(message) {
    const text = message.trim()
    if (!text) return

    setInput('')
    setTrace([])
    setSummary('')
    setWarnings([])
    setKeyActions([])
    setSuggestions([])
    setWorkflowId('')
    setIsLoading(true)

    try {
      const response = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, user_id: 'user_01', stream: true }),
      })

      if (!response.ok || !response.body) {
        throw new Error(`Request failed with ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() || ''

        for (const block of blocks) {
          const event = parseEventBlock(block)
          if (!event) continue
          handleStreamEvent(event.eventType, event.payload)
        }
      }

      await loadDashboard()
    } catch (error) {
      setWarnings([error.message || 'Unable to reach the backend.'])
    } finally {
      setIsLoading(false)
    }
  }

  function handleStreamEvent(eventType, payload) {
    if (eventType === 'trace') {
      setTrace((current) => [...current, payload])
      setAgents((current) =>
        current.map((agent) =>
          agent.name === payload.agent
            ? { ...agent, status: payload.status || 'active', message: payload.message, last_update: payload.timestamp }
            : agent
        )
      )
      return
    }

    if (eventType === 'result') {
      setSummary(payload.summary || '')
      setWarnings(payload.warnings || [])
      setKeyActions(payload.key_actions || [])
      setSuggestions(payload.follow_up_suggestions || [])
      setWorkflowId(payload.workflow_id || '')
      const outputs = payload.workflow?.agent_outputs || {}
      setAgents((current) =>
        current.map((agent) =>
          outputs[agent.name]
            ? {
                ...agent,
                status: outputs[agent.name].status === 'error' ? 'error' : 'done',
                message: outputs[agent.name].summary || outputs[agent.name].error || agent.message,
              }
            : agent
        )
      )
    }
  }

  const heroStats = useMemo(
    () => [
      { label: 'Agents', value: '5' },
      { label: 'Loop', value: '60s' },
      { label: 'Reminder path', value: 'WA -> Voice' },
    ],
    []
  )

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Gen AI Hackathon APAC Edition</p>
          <h1>NEXUS</h1>
          <p className="subtitle">The AI assistant that will not let the deadline disappear.</p>
        </div>
        <div className="topbar-actions">
          <div className={`auth-pill ${auth?.authenticated ? 'connected' : ''}`}>
            <span className="auth-dot" />
            {auth?.authenticated ? auth.email || 'Google connected' : 'Google not connected'}
          </div>
          <button
            className="primary-button"
            onClick={() => {
              window.location.href = '/auth/login'
            }}
          >
            {auth?.authenticated ? 'Reconnect Google' : 'Connect Google'}
          </button>
        </div>
      </header>

      {banner ? <div className="banner">{banner}</div> : null}

      <main className="dashboard">
        <section className="hero-card">
          <div className="hero-copy">
            <p className="hero-tag">Multi-agent workflow intelligence</p>
            <h2>Calendar, tasks, notes, comms, and reminders acting as one live system.</h2>
            <p>
              Start with a natural language request, watch the graph light up, and let the proactive reminder layer
              chase anything you ignore.
            </p>
          </div>
          <div className="hero-stats">
            {heroStats.map((stat) => (
              <div key={stat.label} className="stat-card">
                <span>{stat.label}</span>
                <strong>{stat.value}</strong>
              </div>
            ))}
          </div>
        </section>

        <section className="composer-card">
          <div className="composer-head">
            <div>
              <p className="section-kicker">Command Nexus</p>
              <h3>Run a workflow</h3>
            </div>
            <div className={`run-indicator ${isLoading ? 'active' : ''}`}>
              {isLoading ? 'Streaming trace' : 'Idle'}
            </div>
          </div>
          <form
            className="composer-form"
            onSubmit={(event) => {
              event.preventDefault()
              handleSubmit(input)
            }}
          >
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Set me up for the week."
              rows={3}
            />
            <button className="primary-button" type="submit" disabled={isLoading}>
              {isLoading ? 'Running...' : 'Launch workflow'}
            </button>
          </form>
          <div className="quick-actions">
            {QUICK_ACTIONS.map((action) => (
              <button key={action} className="quick-chip" onClick={() => handleSubmit(action)} type="button">
                {action}
              </button>
            ))}
          </div>
        </section>

        <section className="graph-panel">
          <div className="panel-head">
            <div>
              <p className="section-kicker">Live graph</p>
              <h3>Agent activation map</h3>
            </div>
            <div className="meta-stack">
              <span>Workflow {workflowId ? workflowId.slice(0, 8) : 'standby'}</span>
              <span>{trace.length} trace events</span>
            </div>
          </div>
          <AgentGraph agents={agents} />
        </section>

        <section className="trace-panel">
          <TracePanel
            summary={summary}
            warnings={warnings}
            keyActions={keyActions}
            suggestions={suggestions}
            trace={trace}
            isLoading={isLoading}
            formatTime={formatTime}
          />
          <div ref={traceRef} />
        </section>

        <section className="tasks-panel">
          <div className="panel-head">
            <div>
              <p className="section-kicker">Action queue</p>
              <h3>Ranked tasks</h3>
            </div>
            <span className="meta-pill">{tasks.length} tracked</span>
          </div>
          <div className="list-grid">
            {tasks.slice(0, 6).map((task) => (
              <article key={task.id} className="task-card">
                <div className="task-row">
                  <strong>{task.title}</strong>
                  <span className={`status-tag ${task.status}`}>{task.status}</span>
                </div>
                <p>{task.description || 'No extra description captured yet.'}</p>
                <div className="task-meta">
                  <span>Priority score {task.priority_score ?? task.priority ?? '-'}</span>
                  <span>{formatDate(task.deadline)}</span>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="workflows-panel">
          <div className="panel-head">
            <div>
              <p className="section-kicker">Memory of execution</p>
              <h3>Workflow history</h3>
            </div>
            <span className="meta-pill">{workflows.length} runs</span>
          </div>
          <div className="workflow-list">
            {workflows.slice(0, 5).map((workflow) => (
              <article key={workflow.id} className="workflow-card">
                <div className="task-row">
                  <strong>{workflow.user_intent || 'Untitled workflow'}</strong>
                  <span className={`status-tag ${workflow.status}`}>{workflow.status}</span>
                </div>
                <p>{workflow.plan?.length || 0} planned steps</p>
                <div className="task-meta">
                  <span>{workflow.id.slice(0, 8)}</span>
                  <span>{formatDate(workflow.created_at)}</span>
                </div>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  )
}

function normalizeAgents(agents) {
  const incoming = new Map(agents.map((agent) => [agent.name, agent]))
  return EMPTY_AGENTS.map((agent) => ({ ...agent, ...(incoming.get(agent.name) || {}) }))
}
