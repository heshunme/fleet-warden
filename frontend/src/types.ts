export type TaskMode = "agent_command" | "agent_delegation";

export interface NodeRecord {
  id: number;
  name: string;
  host_alias: string;
  hostname: string;
  port: number;
  username: string | null;
  ssh_config_source: string;
  tags: string[];
  capability_warnings: string[];
  last_seen_at: string | null;
  is_enabled: boolean;
}

export interface TaskSpecRecord {
  id: number;
  task_id: number;
  goal: string;
  constraints: string[];
  success_criteria: string[];
  risk_notes: string[];
  allowed_action_types: string[];
  disallowed_action_types: string[];
  initial_todo_template: string[];
  operator_notes: string | null;
  approved_by: string | null;
  approved_at: string | null;
  version: number;
}

export interface ApprovalRecord {
  id: number;
  decision: string;
  edited_content: Record<string, unknown> | null;
  comment: string | null;
  approved_by: string;
  approved_at: string;
}

export interface ExecutionResultRecord {
  id: number;
  executor_type: string;
  exit_code: number | null;
  stdout: string;
  stderr: string;
  structured_output: Record<string, unknown>;
  execution_summary: string;
  started_at: string | null;
  ended_at: string | null;
  is_action_successful: boolean;
}

export interface ProposalRecord {
  id: number;
  round_id: number;
  task_id: number | null;
  task_node_id: number | null;
  node_label: string | null;
  proposal_type: string;
  summary: string;
  todo_delta: string[];
  rationale: string;
  risk_level: string;
  content: Record<string, unknown>;
  editable_content: Record<string, unknown>;
  success_hypothesis: string;
  status: string;
  needs_user_input: boolean;
  created_at: string;
  approvals: ApprovalRecord[];
  execution_results: ExecutionResultRecord[];
}

export interface NodeAgentStateRecord {
  round_index: number;
  todo_items: string[];
  observations: string[];
  attempted_actions: Array<Record<string, unknown>>;
  success_assessment: string | null;
  status: string;
  snapshot_blob: Record<string, unknown>;
}

export interface RoundRecord {
  id: number;
  task_node_id: number;
  index: number;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  proposals: ProposalRecord[];
}

export interface TaskNodeRecord {
  id: number;
  task_id: number;
  node_id: number;
  status: string;
  current_round: number;
  stop_reason: string | null;
  success_summary: string | null;
  failure_summary: string | null;
  needs_user_input: boolean;
  last_result_at: string | null;
  node: NodeRecord;
  agent_state: NodeAgentStateRecord | null;
  rounds: RoundRecord[];
}

export interface TaskRecord {
  id: number;
  title: string;
  mode: TaskMode;
  user_input: string;
  status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  approved_task_spec_id: number | null;
  max_rounds_per_node: number;
  auto_pause_on_risk: boolean;
  task_specs: TaskSpecRecord[];
  task_nodes: TaskNodeRecord[];
}

export interface EventRecord {
  id: number;
  entity_type: string;
  entity_id: number;
  event_type: string;
  payload: Record<string, unknown>;
  operator_id: string;
  created_at: string | null;
}
