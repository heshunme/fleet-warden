import { cancelTask, pauseTask, resumeTask } from "../lib/api";
import type { EventRecord, TaskRecord } from "../types";
import { SectionCard } from "../components/SectionCard";

interface TaskOverviewPageProps {
  task: TaskRecord | null;
  events: EventRecord[];
  onTaskUpdated: (task: TaskRecord) => void;
  onSelectTaskNode: (taskNodeId: number) => void;
}

export function TaskOverviewPage({ task, events, onTaskUpdated, onSelectTaskNode }: TaskOverviewPageProps) {
  if (!task) {
    return (
      <SectionCard title="Task Overview">
        <p className="muted">No task selected yet.</p>
      </SectionCard>
    );
  }

  const counts = task.task_nodes.reduce<Record<string, number>>((accumulator, node) => {
    accumulator[node.status] = (accumulator[node.status] ?? 0) + 1;
    return accumulator;
  }, {});

  return (
    <SectionCard
      title="Task Overview"
      action={
        <div className="button-row">
          <button className="secondary" onClick={async () => onTaskUpdated(await pauseTask(task.id))} type="button">
            Pause
          </button>
          <button className="secondary" onClick={async () => onTaskUpdated(await resumeTask(task.id))} type="button">
            Resume
          </button>
          <button className="danger" onClick={async () => onTaskUpdated(await cancelTask(task.id))} type="button">
            Cancel
          </button>
        </div>
      }
    >
      <div className="grid-two">
        <div className="stack">
          <div className="stat-grid">
            <div className="stat"><span>Status</span><strong>{task.status}</strong></div>
            <div className="stat"><span>Mode</span><strong>{task.mode}</strong></div>
            <div className="stat"><span>Nodes</span><strong>{task.task_nodes.length}</strong></div>
            <div className="stat"><span>Rounds/Node</span><strong>{task.max_rounds_per_node}</strong></div>
          </div>
          <div className="badge-row">
            {Object.entries(counts).map(([status, count]) => (
              <span key={status} className="badge">
                {status}: {count}
              </span>
            ))}
          </div>
          <table>
            <thead>
              <tr>
                <th>Node</th>
                <th>Status</th>
                <th>Round</th>
                <th>Summary</th>
              </tr>
            </thead>
            <tbody>
              {task.task_nodes.map((taskNode) => (
                <tr key={taskNode.id} onClick={() => onSelectTaskNode(taskNode.id)}>
                  <td>{taskNode.node.host_alias}</td>
                  <td>{taskNode.status}</td>
                  <td>{taskNode.current_round}</td>
                  <td>{taskNode.success_summary ?? taskNode.failure_summary ?? "In progress"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="stack">
          <h3>Latest Events</h3>
          <div className="event-stream">
            {events.slice(-10).reverse().map((event) => (
              <article key={event.id} className="event-row">
                <strong>{event.event_type}</strong>
                <span>{event.created_at ?? "pending"}</span>
                <small>{JSON.stringify(event.payload)}</small>
              </article>
            ))}
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

