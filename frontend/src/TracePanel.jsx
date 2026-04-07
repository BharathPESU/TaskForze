export default function TracePanel({
  summary,
  warnings,
  keyActions,
  suggestions,
  trace,
  isLoading,
  formatTime,
}) {
  return (
    <div className="trace-shell">
      <div className="panel-head">
        <div>
          <p className="section-kicker">Trace stream</p>
          <h3>Execution narrative</h3>
        </div>
        <span className={`run-indicator ${isLoading ? 'active' : ''}`}>{isLoading ? 'Live' : 'Complete'}</span>
      </div>

      <section className="summary-card">
        <strong>Summary</strong>
        <p>{summary || 'Run a workflow to populate the summary panel.'}</p>
      </section>

      <section className="mini-columns">
        <div className="mini-card">
          <strong>Key actions</strong>
          {keyActions.length ? (
            keyActions.map((item) => <p key={item}>{item}</p>)
          ) : (
            <p>No actions yet.</p>
          )}
        </div>
        <div className="mini-card">
          <strong>Warnings</strong>
          {warnings.length ? warnings.map((item) => <p key={item}>{item}</p>) : <p>No warnings.</p>}
        </div>
      </section>

      <section className="summary-card">
        <strong>Follow-up</strong>
        {suggestions.length ? suggestions.map((item) => <p key={item}>{item}</p>) : <p>No follow-up suggestions yet.</p>}
      </section>

      <section className="timeline">
        {trace.length ? (
          trace.map((event, index) => (
            <article key={`${event.timestamp}-${index}`} className={`timeline-item ${event.status || 'idle'}`}>
              <div className="timeline-meta">
                <strong>{event.agent}</strong>
                <span>{formatTime(event.timestamp)}</span>
              </div>
              <p>{event.message}</p>
            </article>
          ))
        ) : (
          <article className="timeline-item idle">
            <div className="timeline-meta">
              <strong>nexus</strong>
              <span>standby</span>
            </div>
            <p>The trace stream will appear here as soon as a workflow starts.</p>
          </article>
        )}
      </section>
    </div>
  )
}
