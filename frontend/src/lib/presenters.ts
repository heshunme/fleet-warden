import type {
  CurrentMode,
  EventRecord,
  PreviewCardModel,
  ProposalRecord,
  RightRailTab,
  TaskRecord,
  TaskSpecRecord,
} from "../types";

const TERMINAL_TASK_STATUSES = new Set(["succeeded", "failed", "partially_succeeded", "cancelled"]);

function stringifyValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return `${value.length} item${value.length === 1 ? "" : "s"}`;
  }
  if (value && typeof value === "object") {
    return `${Object.keys(value as Record<string, unknown>).length} fields`;
  }
  return "empty";
}

export function formatTimestamp(value: string | null): string {
  if (!value) {
    return "N/A";
  }
  return new Date(value).toLocaleString();
}

export function truncateText(value: string | null | undefined, max = 140): string {
  if (!value) {
    return "N/A";
  }
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

export function summarizeTask(task: TaskRecord | null): string {
  if (!task) {
    return "No active task selected.";
  }
  if (task.status === "awaiting_taskspec_approval") {
    return "Review the generated TaskSpec before node work can continue.";
  }
  if (TERMINAL_TASK_STATUSES.has(task.status)) {
    return "This task has finished. Review outcomes or switch to another task.";
  }
  return "The console keeps the next required action in focus and moves details into the side drawer.";
}

export function getDefaultRightRailTab(mode: CurrentMode): RightRailTab {
  return mode === "proposal" ? "inspector" : "progress";
}

export function buildTaskSpecCounters(taskSpec: TaskSpecRecord | null): Array<{ label: string; count: number }> {
  return [
    { label: "Constraints", count: taskSpec?.constraints.length ?? 0 },
    { label: "Success", count: taskSpec?.success_criteria.length ?? 0 },
    { label: "Risk Notes", count: taskSpec?.risk_notes.length ?? 0 },
    { label: "Initial Todo", count: taskSpec?.initial_todo_template.length ?? 0 },
  ];
}

export function buildEditableContentPreview(editableContent: Record<string, unknown>): PreviewCardModel {
  const commands = editableContent.commands;
  if (Array.isArray(commands) && commands.every((command) => typeof command === "string")) {
    const lines = commands.slice(0, 3).map((command) => `$ ${command}`);
    const hiddenCount = Math.max(0, commands.length - lines.length);
    return {
      title: `${commands.length} command${commands.length === 1 ? "" : "s"} ready`,
      description: "First commands from the proposed payload",
      lines,
      footer: hiddenCount > 0 ? `+${hiddenCount} more commands in the full payload` : null,
      variant: "code",
    };
  }

  const entries = Object.entries(editableContent);
  if (entries.length > 0) {
    const lines = entries.slice(0, 6).map(([key, value]) => `${key}: ${stringifyValue(value)}`);
    const hiddenCount = Math.max(0, entries.length - lines.length);
    return {
      title: `${entries.length} payload field${entries.length === 1 ? "" : "s"}`,
      description: "Top-level fields surfaced for quick review",
      lines,
      footer: hiddenCount > 0 ? `+${hiddenCount} more fields in the full payload` : null,
      variant: "structured",
    };
  }

  const jsonPreview = JSON.stringify(editableContent, null, 2).split("\n").slice(0, 6);
  return {
    title: "JSON payload preview",
    description: "A short preview of the raw JSON payload",
    lines: jsonPreview,
    footer: "Open the drawer to inspect the full payload",
    variant: "json",
  };
}

export function describeEvent(event: EventRecord): string {
  const payloadText = truncateText(JSON.stringify(event.payload), 90);
  return `${event.event_type} · ${payloadText}`;
}

export function summarizeProposalContext(proposal: ProposalRecord): {
  todoDelta: string[];
  rationale: string;
  successHypothesis: string;
} {
  return {
    todoDelta: proposal.todo_delta.slice(0, 3),
    rationale: truncateText(proposal.rationale, 220),
    successHypothesis: truncateText(proposal.success_hypothesis, 180),
  };
}
