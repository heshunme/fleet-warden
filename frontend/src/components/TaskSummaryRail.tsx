import { buildTaskSpecCounters, formatTimestamp, truncateText } from "../lib/presenters";
import type { CurrentMode, TaskRecord, TaskSpecRecord } from "../types";

interface TaskSummaryRailProps {
  currentMode: CurrentMode;
  task: TaskRecord | null;
  taskSpec: TaskSpecRecord | null;
  onOpenTaskSpec: () => void;
}

export function TaskSummaryRail({ currentMode, task, taskSpec, onOpenTaskSpec }: TaskSummaryRailProps) {
  const counters = buildTaskSpecCounters(taskSpec);

  return (
    <section className="panel rail-panel">
      <div className="panel-header">
        <div>
          <h2>Task Summary</h2>
        </div>
        <span className={`pill pill-${task?.status ?? "idle"}`}>{task?.status ?? "idle"}</span>
      </div>

      <div className="panel-body summary-rail-layout">
        {currentMode === "taskspec" ? (
          <div className="summary-card notice-card">
            <span className="section-label">TaskSpec Pending</span>
            <p>Approval is still required before per-node work can continue.</p>
          </div>
        ) : null}

        <div className="stat-grid compact-stats summary-stats">
          <div className="stat">
            <span>Mode</span>
            <strong>{task?.mode ?? "N/A"}</strong>
          </div>
          <div className="stat">
            <span>Nodes</span>
            <strong>{task?.task_nodes.length ?? 0}</strong>
          </div>
          <div className="stat">
            <span>Rounds</span>
            <strong>{task?.max_rounds_per_node ?? 0}</strong>
          </div>
          <div className="stat">
            <span>Updated</span>
            <strong>{task ? formatTimestamp(task.updated_at) : "N/A"}</strong>
          </div>
        </div>

        <div className="summary-card">
          <span className="section-label">Operator Goal</span>
          <p className="clamp-2">{truncateText(task?.user_input, 180)}</p>
        </div>

        <div className="summary-card">
          <span className="section-label">TaskSpec Goal</span>
          <p className="clamp-2">{truncateText(taskSpec?.goal, 180)}</p>
        </div>

        <div className="summary-card">
          <span className="section-label">TaskSpec Snapshot</span>
          <div className="token-row">
            {counters.map((counter) => (
              <span key={counter.label} className="token token-static count-token">
                {counter.label} {counter.count}
              </span>
            ))}
          </div>
        </div>

        <button className="secondary" type="button" onClick={onOpenTaskSpec} disabled={!taskSpec}>
          View Full TaskSpec
        </button>
      </div>
    </section>
  );
}
