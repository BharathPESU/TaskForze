const POSITIONS = {
  orchestrator: { x: 50, y: 16 },
  calendar: { x: 14, y: 66 },
  task: { x: 32, y: 66 },
  notes: { x: 50, y: 66 },
  comms: { x: 68, y: 66 },
  reminder: { x: 86, y: 66 },
}

const LABELS = {
  orchestrator: 'Orchestrator',
  calendar: 'Calendar',
  task: 'Task',
  notes: 'Notes',
  comms: 'Comms',
  reminder: 'Reminder',
}

const EDGES = [
  ['orchestrator', 'calendar'],
  ['orchestrator', 'task'],
  ['orchestrator', 'notes'],
  ['orchestrator', 'comms'],
  ['orchestrator', 'reminder'],
  ['notes', 'comms'],
  ['task', 'comms'],
  ['task', 'reminder'],
]

export default function AgentGraph({ agents }) {
  const byName = Object.fromEntries(agents.map((agent) => [agent.name, agent]))

  return (
    <div className="graph-stage">
      <svg className="graph-edges" viewBox="0 0 100 100" preserveAspectRatio="none">
        {EDGES.map(([source, target]) => {
          const active = byName[target]?.status === 'active'
          return (
            <line
              key={`${source}-${target}`}
              x1={POSITIONS[source].x}
              y1={POSITIONS[source].y}
              x2={POSITIONS[target].x}
              y2={POSITIONS[target].y}
              className={active ? 'edge edge-active' : 'edge'}
            />
          )
        })}
      </svg>

      {agents.map((agent) => (
        <article
          key={agent.name}
          className={`agent-node ${agent.status}`}
          style={{
            left: `${POSITIONS[agent.name]?.x || 50}%`,
            top: `${POSITIONS[agent.name]?.y || 50}%`,
          }}
        >
          <div className="node-head">
            <span className="node-dot" />
            <strong>{LABELS[agent.name] || agent.name}</strong>
          </div>
          <p>{agent.message || 'Waiting'}</p>
          <span className="node-status">{agent.status}</span>
        </article>
      ))}
    </div>
  )
}
