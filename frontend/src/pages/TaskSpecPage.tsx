import { useEffect, useState } from "react";

import { approveTaskSpec, fetchTaskSpec, rejectTaskSpec } from "../lib/api";
import { canApproveTaskSpec, canRejectTaskSpec } from "../lib/guards";
import type { TaskRecord, TaskSpecRecord } from "../types";
import { SectionCard } from "../components/SectionCard";

interface TaskSpecPageProps {
  task: TaskRecord | null;
  onTaskUpdated: (task: TaskRecord) => void;
}

export function TaskSpecPage({ task, onTaskUpdated }: TaskSpecPageProps) {
  const [taskSpec, setTaskSpec] = useState<TaskSpecRecord | null>(null);
  const [draftGoal, setDraftGoal] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!task) {
      setTaskSpec(null);
      return;
    }
    fetchTaskSpec(task.id).then((data) => {
      setTaskSpec(data);
      setDraftGoal(data.goal);
    });
  }, [task]);

  if (!task) {
    return (
      <SectionCard title="TaskSpec Approval">
        <p className="muted">Create or select a task to review its TaskSpec draft.</p>
      </SectionCard>
    );
  }

  if (!taskSpec) {
    return (
      <SectionCard title="TaskSpec Approval">
        <p className="muted">Loading TaskSpec...</p>
      </SectionCard>
    );
  }

  const approve = async () => {
    setIsSubmitting(true);
    try {
      const updated = await approveTaskSpec(task.id, { goal: draftGoal });
      onTaskUpdated(updated);
    } finally {
      setIsSubmitting(false);
    }
  };

  const reject = async () => {
    setIsSubmitting(true);
    try {
      const updated = await rejectTaskSpec(task.id, "Rejected from UI");
      onTaskUpdated(updated);
    } finally {
      setIsSubmitting(false);
    }
  };

  const canApprove = canApproveTaskSpec(task) && !isSubmitting;
  const canReject = canRejectTaskSpec(task) && !isSubmitting;

  return (
    <SectionCard title="TaskSpec Approval">
      <div className="stack">
        <label>
          <span>Goal</span>
          <textarea
            rows={3}
            value={draftGoal}
            onChange={(event) => setDraftGoal(event.target.value)}
            disabled={!canApprove}
          />
        </label>
        {!canApproveTaskSpec(task) || !canRejectTaskSpec(task) ? (
          <p className="muted">
            TaskSpec actions are only available before execution starts. Rejected or cancelled tasks cannot be re-approved.
          </p>
        ) : null}
        <div className="badge-row">
          {taskSpec.allowed_action_types.map((item) => (
            <span key={item} className="badge">{item}</span>
          ))}
        </div>
        <div className="grid-two">
          <div>
            <h3>Constraints</h3>
            <ul>{taskSpec.constraints.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
          <div>
            <h3>Success Criteria</h3>
            <ul>{taskSpec.success_criteria.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        </div>
        <div className="grid-two">
          <div>
            <h3>Risk Notes</h3>
            <ul>{taskSpec.risk_notes.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
          <div>
            <h3>Initial Todo</h3>
            <ul>{taskSpec.initial_todo_template.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        </div>
        <div className="button-row">
          <button onClick={approve} type="button" disabled={!canApprove}>Approve TaskSpec</button>
          <button className="secondary" onClick={reject} type="button" disabled={!canReject}>Reject</button>
        </div>
      </div>
    </SectionCard>
  );
}
