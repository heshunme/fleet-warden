import { useState } from "react";

import { cancelTask, pauseTask, resumeTask } from "../lib/api";
import { canCancelTask, canPauseTask, canResumeTask } from "../lib/guards";
import type { EventRecord, TaskRecord } from "../types";
import { SectionCard } from "../components/SectionCard";

interface TaskOverviewPageProps {
  task: TaskRecord | null;
  events: EventRecord[];
  onTaskUpdated: (task: TaskRecord) => void;
  onSelectTaskNode: (taskNodeId: number) => void;
}

export function TaskOverviewPage({ task, events, onTaskUpdated, onSelectTaskNode }: TaskOverviewPageProps) {
  const [busyAction, setBusyAction] = useState<string | null>(null);

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
  const pauseDisabled = !canPauseTask(task) || busyAction !== null;
  const resumeDisabled = !canResumeTask(task) || busyAction !== null;
  const cancelDisabled = !canCancelTask(task) || busyAction !== null;

  const runTaskAction = async (action: "pause" | "resume" | "cancel") => {
    setBusyAction(action);
    try {
      if (action === "pause") {
        onTaskUpdated(await pauseTask(task.id));
      } else if (action === "resume") {
        onTaskUpdated(await resumeTask(task.id));
      } else {
        onTaskUpdated(await cancelTask(task.id));
      }
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <SectionCard
      title="Task Overview"
      action={
        <div className="button-row">
          <button
            className="secondary"
            onClick={() => runTaskAction("pause")}
            type="button"
            disabled={pauseDisabled}
          >
            Pause
          </button>
          <button
            className="secondary"
            onClick={() => runTaskAction("resume")}
            type="button"
            disabled={resumeDisabled}
          >
            Resume
          </button>
          <button
            className="danger"
            onClick={() => runTaskAction("cancel")}
            type="button"
            disabled={cancelDisabled}
          >
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
          <p className="muted">
            Pause is only available while a task is waiting for TaskSpec approval or actively running. Resume only works from paused, and cancel is disabled once a task is terminal.
          </p>
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
