import type { ProposalRecord, TaskRecord } from "../types";


const TERMINAL_TASK_STATUSES = new Set([
  "succeeded",
  "failed",
  "partially_succeeded",
  "cancelled",
]);


export function canApproveTaskSpec(task: TaskRecord): boolean {
  return task.status === "awaiting_taskspec_approval" && task.approved_task_spec_id === null;
}


export function canRejectTaskSpec(task: TaskRecord): boolean {
  return (
    task.approved_task_spec_id === null
    && (task.status === "awaiting_taskspec_approval" || task.status === "paused")
  );
}


export function canPauseTask(task: TaskRecord): boolean {
  return task.status === "awaiting_taskspec_approval" || task.status === "running";
}


export function canResumeTask(task: TaskRecord): boolean {
  return task.status === "paused";
}


export function canCancelTask(task: TaskRecord): boolean {
  return !TERMINAL_TASK_STATUSES.has(task.status);
}


export function canHandleProposal(proposal: ProposalRecord): boolean {
  return proposal.status === "pending";
}
