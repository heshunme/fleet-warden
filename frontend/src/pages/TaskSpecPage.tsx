import { useEffect, useState } from "react";

import { approveTaskSpec, fetchTaskSpec, rejectTaskSpec } from "../lib/api";
import type { TaskRecord, TaskSpecRecord } from "../types";
import { SectionCard } from "../components/SectionCard";

interface TaskSpecPageProps {
  task: TaskRecord | null;
  onTaskUpdated: (task: TaskRecord) => void;
}

export function TaskSpecPage({ task, onTaskUpdated }: TaskSpecPageProps) {
  const [taskSpec, setTaskSpec] = useState<TaskSpecRecord | null>(null);
  const [draftGoal, setDraftGoal] = useState("");

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
    const updated = await approveTaskSpec(task.id, { goal: draftGoal });
    onTaskUpdated(updated);
  };

  const reject = async () => {
    const updated = await rejectTaskSpec(task.id, "Rejected from UI");
    onTaskUpdated(updated);
  };

  return (
    <SectionCard title="TaskSpec Approval">
      <div className="stack">
        <label>
          <span>Goal</span>
          <textarea rows={3} value={draftGoal} onChange={(event) => setDraftGoal(event.target.value)} />
        </label>
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
          <button onClick={approve} type="button">Approve TaskSpec</button>
          <button className="secondary" onClick={reject} type="button">Reject</button>
        </div>
      </div>
    </SectionCard>
  );
}

