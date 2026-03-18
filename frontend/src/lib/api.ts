import type {
  EventRecord,
  NodeRecord,
  ProposalRecord,
  TaskNodeRecord,
  TaskRecord,
  TaskSpecRecord,
  TaskMode,
} from "../types";

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

export function buildApiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchNodes(): Promise<NodeRecord[]> {
  return request<NodeRecord[]>("/nodes");
}

export function refreshNodes(): Promise<NodeRecord[]> {
  return request<NodeRecord[]>("/nodes/refresh", { method: "POST" });
}

export function createTask(payload: {
  mode: TaskMode;
  user_input: string;
  node_ids: number[];
  max_rounds_per_node: number;
}): Promise<TaskRecord> {
  return request<TaskRecord>("/tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchTasks(): Promise<TaskRecord[]> {
  return request<TaskRecord[]>("/tasks");
}

export function fetchTask(taskId: number): Promise<TaskRecord> {
  return request<TaskRecord>(`/tasks/${taskId}`);
}

export function pauseTask(taskId: number): Promise<TaskRecord> {
  return request<TaskRecord>(`/tasks/${taskId}/pause`, { method: "POST" });
}

export function resumeTask(taskId: number): Promise<TaskRecord> {
  return request<TaskRecord>(`/tasks/${taskId}/resume`, { method: "POST" });
}

export function cancelTask(taskId: number): Promise<TaskRecord> {
  return request<TaskRecord>(`/tasks/${taskId}/cancel`, { method: "POST" });
}

export function fetchTaskSpec(taskId: number): Promise<TaskSpecRecord> {
  return request<TaskSpecRecord>(`/tasks/${taskId}/taskspec`);
}

export function approveTaskSpec(taskId: number, payload: Partial<TaskSpecRecord>): Promise<TaskRecord> {
  return request<TaskRecord>(`/tasks/${taskId}/taskspec/approve`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function rejectTaskSpec(taskId: number, comment: string): Promise<TaskRecord> {
  return request<TaskRecord>(`/tasks/${taskId}/taskspec/reject`, {
    method: "POST",
    body: JSON.stringify({ comment }),
  });
}

export function fetchPendingProposals(): Promise<ProposalRecord[]> {
  return request<ProposalRecord[]>("/proposals?status=pending");
}

export function approveProposal(
  proposalId: number,
  payload: { edited_content?: Record<string, unknown> | null; comment?: string | null }
): Promise<ProposalRecord> {
  return request<ProposalRecord>(`/proposals/${proposalId}/approve`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function rejectProposal(proposalId: number, comment: string): Promise<ProposalRecord> {
  return request<ProposalRecord>(`/proposals/${proposalId}/reject`, {
    method: "POST",
    body: JSON.stringify({ comment }),
  });
}

export function pauseProposalNode(proposalId: number, comment: string): Promise<ProposalRecord> {
  return request<ProposalRecord>(`/proposals/${proposalId}/pause-node`, {
    method: "POST",
    body: JSON.stringify({ comment }),
  });
}

export function fetchTaskNodes(taskId: number): Promise<TaskNodeRecord[]> {
  return request<TaskNodeRecord[]>(`/tasks/${taskId}/nodes`);
}

export function fetchTaskNode(taskNodeId: number): Promise<TaskNodeRecord> {
  return request<TaskNodeRecord>(`/task-nodes/${taskNodeId}`);
}

export function fetchTaskEvents(taskId: number): Promise<EventRecord[]> {
  return request<EventRecord[]>(`/tasks/${taskId}/events?after_id=0`);
}
