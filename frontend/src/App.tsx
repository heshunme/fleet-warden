import { useEffect, useMemo, useRef, useState } from "react";

import "./styles.css";
import {
  approveProposal,
  approveTaskSpec,
  buildApiUrl,
  cancelTask,
  createTask,
  fetchNodes,
  fetchPendingProposals,
  fetchTask,
  fetchTaskEvents,
  fetchTaskNode,
  fetchTaskSpec,
  fetchTasks,
  pauseProposalNode,
  pauseTask,
  refreshNodes,
  rejectProposal,
  rejectTaskSpec,
  resumeTask,
} from "./lib/api";
import { canApproveTaskSpec, canCancelTask, canPauseTask, canRejectTaskSpec, canResumeTask } from "./lib/guards";
import type {
  EventRecord,
  ExecutionResultRecord,
  NodeRecord,
  ProposalRecord,
  TaskMode,
  TaskNodeRecord,
  TaskRecord,
  TaskSpecRecord,
} from "./types";

const TERMINAL_TASK_STATUSES = new Set(["succeeded", "failed", "partially_succeeded", "cancelled"]);

function connectEvents(path: string, onEvent: () => void) {
  const source = new EventSource(buildApiUrl(path));
  source.onmessage = () => onEvent();
  return () => source.close();
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "N/A";
  }
  return new Date(value).toLocaleString();
}

function summarizeTask(task: TaskRecord | null): string {
  if (!task) {
    return "No active task selected.";
  }
  if (task.status === "awaiting_taskspec_approval") {
    return "Review the generated TaskSpec before any node work can continue.";
  }
  if (TERMINAL_TASK_STATUSES.has(task.status)) {
    return "This task has reached a terminal state. Review outcomes and switch tasks if needed.";
  }
  return "The system will keep surfacing the next proposal or wait state for this task here.";
}

type TaskAction = "pause" | "resume" | "cancel";

function App() {
  const currentTaskIdRef = useRef<number | null>(null);
  const reloadSequenceRef = useRef(0);
  const [nodes, setNodes] = useState<NodeRecord[]>([]);
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [currentTaskId, setCurrentTaskId] = useState<number | null>(null);
  const [currentTask, setCurrentTask] = useState<TaskRecord | null>(null);
  const [currentTaskSpec, setCurrentTaskSpec] = useState<TaskSpecRecord | null>(null);
  const [pendingProposals, setPendingProposals] = useState<ProposalRecord[]>([]);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [inspectedTaskNodeId, setInspectedTaskNodeId] = useState<number | null>(null);
  const [inspectedTaskNode, setInspectedTaskNode] = useState<TaskNodeRecord | null>(null);
  const [isNodePinned, setIsNodePinned] = useState(false);
  const [isCreatingTask, setIsCreatingTask] = useState(false);
  const [isBooting, setIsBooting] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [nodeQuery, setNodeQuery] = useState("");
  const [selectedNodeIds, setSelectedNodeIds] = useState<number[]>([]);
  const [title, setTitle] = useState("FleetWarden V1 Task");
  const [mode, setMode] = useState<TaskMode>("agent_command");
  const [userInput, setUserInput] = useState("Inspect current node state and report back the next safe action.");
  const [maxRoundsPerNode, setMaxRoundsPerNode] = useState(3);
  const [goalDraft, setGoalDraft] = useState("");
  const [approvalComment, setApprovalComment] = useState("Approved from UI");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [isRefreshingNodes, setIsRefreshingNodes] = useState(false);

  const reloadDashboard = async (preferredTaskId?: number | null) => {
    const reloadId = reloadSequenceRef.current + 1;
    reloadSequenceRef.current = reloadId;

    try {
      const [nodeData, taskData, proposalData] = await Promise.all([
        fetchNodes(),
        fetchTasks(),
        fetchPendingProposals(),
      ]);

      if (reloadSequenceRef.current !== reloadId) {
        return;
      }

      setNodes(nodeData);
      setTasks(taskData);
      setPendingProposals(proposalData);

      const preferredSelection = preferredTaskId ?? currentTaskIdRef.current;
      const selectedTaskStillExists = preferredSelection
        ? taskData.some((task) => task.id === preferredSelection)
        : false;

      const nextTaskId =
        selectedTaskStillExists
          ? preferredSelection
          : taskData[0]?.id ?? null;

      if (nextTaskId) {
        const task = await fetchTask(nextTaskId);
        if (reloadSequenceRef.current !== reloadId) {
          return;
        }
        setCurrentTaskId(task.id);
        currentTaskIdRef.current = task.id;
        setCurrentTask(task);
      } else {
        setCurrentTaskId(null);
        currentTaskIdRef.current = null;
        setCurrentTask(null);
        setCurrentTaskSpec(null);
        setEvents([]);
      }

      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unknown error");
    } finally {
      setIsBooting(false);
    }
  };

  useEffect(() => {
    reloadDashboard().catch(() => undefined);
  }, []);

  useEffect(() => {
    currentTaskIdRef.current = currentTaskId;
  }, [currentTaskId]);

  useEffect(() => {
    if (!currentTaskId) {
      setCurrentTask(null);
      setCurrentTaskSpec(null);
      setEvents([]);
      return;
    }

    fetchTask(currentTaskId).then(setCurrentTask).catch(() => undefined);
    fetchTaskEvents(currentTaskId)
      .then((data) => setEvents(data.slice(-12)))
      .catch(() => undefined);
    fetchTaskSpec(currentTaskId)
      .then((data) => {
        setCurrentTaskSpec(data);
        setGoalDraft(data.goal);
      })
      .catch(() => {
        setCurrentTaskSpec(null);
        setGoalDraft("");
      });
  }, [currentTaskId]);

  useEffect(() => {
    if (!currentTaskId) {
      return undefined;
    }

    return connectEvents(`/tasks/${currentTaskId}/events`, () => {
      reloadDashboard(currentTaskId).catch(() => undefined);
    });
  }, [currentTaskId]);

  useEffect(() => connectEvents("/proposals/events", () => {
    reloadDashboard(currentTaskId).catch(() => undefined);
  }), [currentTaskId]);

  const currentTaskProposals = useMemo(
    () => pendingProposals.filter((proposal) => proposal.task_id === currentTaskId),
    [currentTaskId, pendingProposals]
  );

  const activeProposal = currentTaskProposals[0] ?? null;

  useEffect(() => {
    if (isNodePinned) {
      return;
    }

    if (activeProposal?.task_node_id) {
      setInspectedTaskNodeId(activeProposal.task_node_id);
      return;
    }

    if (currentTask?.task_nodes[0]) {
      setInspectedTaskNodeId(currentTask.task_nodes[0].id);
      return;
    }

    setInspectedTaskNodeId(null);
  }, [activeProposal?.id, activeProposal?.task_node_id, currentTask?.id, currentTask?.task_nodes, isNodePinned]);

  useEffect(() => {
    if (!inspectedTaskNodeId) {
      setInspectedTaskNode(null);
      return;
    }
    fetchTaskNode(inspectedTaskNodeId).then(setInspectedTaskNode).catch(() => undefined);
  }, [inspectedTaskNodeId]);

  const filteredNodes = useMemo(
    () =>
      nodes.filter((node) =>
        [node.name, node.host_alias, node.hostname].join(" ").toLowerCase().includes(nodeQuery.toLowerCase())
      ),
    [nodeQuery, nodes]
  );

  const selectedNodes = useMemo(
    () => nodes.filter((node) => selectedNodeIds.includes(node.id)),
    [nodes, selectedNodeIds]
  );

  const summaryCounts = useMemo(() => {
    return tasks.reduce(
      (accumulator, task) => {
        if (task.status === "awaiting_taskspec_approval") {
          accumulator.awaitingTaskSpec += 1;
        }
        if (task.status === "running") {
          accumulator.running += 1;
        }
        if (task.status === "paused") {
          accumulator.paused += 1;
        }
        return accumulator;
      },
      { awaitingTaskSpec: 0, running: 0, paused: 0 }
    );
  }, [tasks]);

  const nodeStatusCounts = useMemo(() => {
    return (currentTask?.task_nodes ?? []).reduce<Record<string, number>>((accumulator, taskNode) => {
      accumulator[taskNode.status] = (accumulator[taskNode.status] ?? 0) + 1;
      return accumulator;
    }, {});
  }, [currentTask?.task_nodes]);

  const hasAwaitingProposalNode = useMemo(
    () => (currentTask?.task_nodes ?? []).some((taskNode) => taskNode.status === "awaiting_proposal"),
    [currentTask?.task_nodes]
  );

  const currentMode = useMemo<"create" | "taskspec" | "proposal" | "terminal" | "awaiting-proposal" | "running">(() => {
    if (isCreatingTask || !currentTask) {
      return "create";
    }
    if (canApproveTaskSpec(currentTask) || canRejectTaskSpec(currentTask)) {
      return "taskspec";
    }
    if (activeProposal) {
      return "proposal";
    }
    if (TERMINAL_TASK_STATUSES.has(currentTask.status)) {
      return "terminal";
    }
    if (hasAwaitingProposalNode) {
      return "awaiting-proposal";
    }
    return "running";
  }, [activeProposal, currentTask, hasAwaitingProposalNode, isCreatingTask]);

  const toggleNode = (nodeId: number) => {
    setSelectedNodeIds((current) =>
      current.includes(nodeId) ? current.filter((id) => id !== nodeId) : [...current, nodeId]
    );
  };

  const removeNode = (nodeId: number) => {
    setSelectedNodeIds((current) => current.filter((id) => id !== nodeId));
  };

  const handleRefreshNodes = async () => {
    setIsRefreshingNodes(true);
    try {
      const refreshed = await refreshNodes();
      setNodes(refreshed);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to refresh nodes");
    } finally {
      setIsRefreshingNodes(false);
    }
  };

  const handleCreateTask = async () => {
    setBusyAction("create-task");
    try {
      const task = await createTask({
        title,
        mode,
        user_input: userInput,
        node_ids: selectedNodeIds,
        max_rounds_per_node: maxRoundsPerNode,
      });
      setCurrentTaskId(task.id);
      setCurrentTask(task);
      setIsCreatingTask(false);
      setSelectedNodeIds([]);
      await reloadDashboard(task.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to create task");
    } finally {
      setBusyAction(null);
    }
  };

  const handleTaskAction = async (action: TaskAction) => {
    if (!currentTask) {
      return;
    }
    setBusyAction(action);
    try {
      const updated =
        action === "pause"
          ? await pauseTask(currentTask.id)
          : action === "resume"
            ? await resumeTask(currentTask.id)
            : await cancelTask(currentTask.id);

      setCurrentTask(updated);
      await reloadDashboard(updated.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Task action failed");
    } finally {
      setBusyAction(null);
    }
  };

  const handleApproveTaskSpec = async () => {
    if (!currentTask) {
      return;
    }
    setBusyAction("approve-taskspec");
    try {
      const updated = await approveTaskSpec(currentTask.id, { goal: goalDraft });
      setCurrentTask(updated);
      await reloadDashboard(updated.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to approve TaskSpec");
    } finally {
      setBusyAction(null);
    }
  };

  const handleRejectTaskSpec = async () => {
    if (!currentTask) {
      return;
    }
    setBusyAction("reject-taskspec");
    try {
      const updated = await rejectTaskSpec(currentTask.id, "Rejected from UI");
      setCurrentTask(updated);
      await reloadDashboard(updated.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to reject TaskSpec");
    } finally {
      setBusyAction(null);
    }
  };

  const handleProposalAction = async (action: "approve" | "reject" | "pause-node") => {
    if (!activeProposal) {
      return;
    }
    setBusyAction(`${action}-${activeProposal.id}`);
    try {
      if (action === "approve") {
        await approveProposal(activeProposal.id, { comment: approvalComment });
      } else if (action === "reject") {
        await rejectProposal(activeProposal.id, approvalComment);
      } else {
        await pauseProposalNode(activeProposal.id, approvalComment);
      }
      await reloadDashboard(currentTaskId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to handle proposal");
    } finally {
      setBusyAction(null);
    }
  };

  const inspectNode = (taskNodeId: number, pinned: boolean) => {
    setInspectedTaskNodeId(taskNodeId);
    setIsNodePinned(pinned);
  };

  const selectedNodeSummary =
    selectedNodes.length > 0
      ? `${selectedNodes.length} node${selectedNodes.length === 1 ? "" : "s"} selected`
      : "Choose at least one node to initialize a task.";

  const latestResult = inspectedTaskNode?.rounds.at(-1)?.proposals.at(-1)?.execution_results.at(-1) ?? null;
  const latestProposal = inspectedTaskNode?.rounds.at(-1)?.proposals.at(-1) ?? null;

  return (
    <main className="workbench">
      <header className="topbar">
        <div className="brand-block">
          <p className="eyebrow">FleetWarden</p>
          <h1>Single-Screen Ops Console</h1>
        </div>

        <div className="topbar-controls">
          <label className="task-switcher">
            <span>Current Task</span>
              <select
                value={currentTaskId ?? ""}
                onChange={(event) => {
                  const rawValue = event.target.value;
                  setIsCreatingTask(false);
                  const nextTaskId = rawValue ? Number(rawValue) : null;
                  currentTaskIdRef.current = nextTaskId;
                  setCurrentTaskId(nextTaskId);
                }}
              >
              <option value="">No task selected</option>
              {tasks.map((task) => (
                <option key={task.id} value={task.id}>
                  #{task.id} {task.title}
                </option>
              ))}
            </select>
          </label>

          <div className="status-strip">
            <span className="signal">TaskSpec {summaryCounts.awaitingTaskSpec}</span>
            <span className="signal">Pending Proposals {pendingProposals.length}</span>
            <span className="signal">Running {summaryCounts.running}</span>
            <span className="signal">Paused {summaryCounts.paused}</span>
          </div>

          <button type="button" onClick={() => setIsCreatingTask(true)}>
            New Task
          </button>
        </div>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      <section className="workspace-grid">
        <aside className="column column-left">
          {currentMode === "create" ? (
            <section className="panel fill-panel">
              <div className="panel-header">
                <h2>Node Selection</h2>
                <button className="secondary" type="button" onClick={handleRefreshNodes} disabled={isRefreshingNodes}>
                  {isRefreshingNodes ? "Refreshing..." : "Refresh SSH Nodes"}
                </button>
              </div>
              <div className="panel-body setup-grid">
                <label>
                  <span>Search Nodes</span>
                  <input
                    value={nodeQuery}
                    onChange={(event) => setNodeQuery(event.target.value)}
                    placeholder="host, alias, hostname"
                  />
                </label>

                <div className="selection-summary">
                  <strong>{selectedNodeSummary}</strong>
                  <div className="token-row">
                    {selectedNodes.map((node) => (
                      <button
                        key={node.id}
                        type="button"
                        className="token"
                        onClick={() => removeNode(node.id)}
                      >
                        {node.host_alias}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="scroll-card node-picker-list">
                  {filteredNodes.map((node) => {
                    const selected = selectedNodeIds.includes(node.id);
                    return (
                      <button
                        key={node.id}
                        type="button"
                        className={`picker-row ${selected ? "picker-row-active" : ""}`}
                        onClick={() => toggleNode(node.id)}
                      >
                        <div>
                          <strong>{node.host_alias}</strong>
                          <span>{node.username ?? "root"}@{node.hostname}:{node.port}</span>
                          {node.capability_warnings[0] ? <small>{node.capability_warnings.join(", ")}</small> : null}
                        </div>
                        <span className="picker-state">{selected ? "Selected" : "Add"}</span>
                      </button>
                    );
                  })}
                  {filteredNodes.length === 0 ? <p className="muted">No nodes match the current query.</p> : null}
                </div>
              </div>
            </section>
          ) : (
            <section className="panel fill-panel">
              <div className="panel-header">
                <h2>Task Context</h2>
                <span className={`pill pill-${currentTask?.status ?? "idle"}`}>{currentTask?.status ?? "idle"}</span>
              </div>
              <div className="panel-body info-grid">
                <div className="stat-grid compact-stats">
                  <div className="stat">
                    <span>Mode</span>
                    <strong>{currentTask?.mode ?? "N/A"}</strong>
                  </div>
                  <div className="stat">
                    <span>Nodes</span>
                    <strong>{currentTask?.task_nodes.length ?? 0}</strong>
                  </div>
                  <div className="stat">
                    <span>Rounds</span>
                    <strong>{currentTask?.max_rounds_per_node ?? 0}</strong>
                  </div>
                  <div className="stat">
                    <span>Updated</span>
                    <strong>{currentTask ? formatTimestamp(currentTask.updated_at) : "N/A"}</strong>
                  </div>
                </div>

                <div className="context-block">
                  <span className="section-label">Operator Goal</span>
                  <p>{currentTask?.user_input ?? "No current task selected."}</p>
                </div>

                <div className="context-block">
                  <span className="section-label">TaskSpec Goal</span>
                  <p>{currentTaskSpec?.goal ?? "TaskSpec not available yet."}</p>
                </div>

                <div className="context-lists">
                  <CompactList title="Constraints" items={currentTaskSpec?.constraints ?? []} />
                  <CompactList title="Success Criteria" items={currentTaskSpec?.success_criteria ?? []} />
                  <CompactList title="Risk Notes" items={currentTaskSpec?.risk_notes ?? []} />
                  <CompactList title="Initial Todo" items={currentTaskSpec?.initial_todo_template ?? []} />
                </div>
              </div>
            </section>
          )}
        </aside>

        <section className="column column-main">
          <section className="panel fill-panel action-panel">
            <div className="panel-header">
              <div>
                <h2>Action Console</h2>
                <p className="muted">{summarizeTask(currentTask)}</p>
              </div>
              {currentMode === "proposal" ? (
                <span className="signal">{currentTaskProposals.length} pending in this task</span>
              ) : null}
            </div>

            <div className="panel-body">
              {currentMode === "create" ? (
                <div className="main-stage">
                  <div className="action-intro">
                    <h3>Initialize a new task</h3>
                    <p className="muted">
                      Define the task once, then the console will keep bringing the next approval or wait state to the center.
                    </p>
                  </div>

                  <div className="form-grid">
                    <label>
                      <span>Title</span>
                      <input value={title} onChange={(event) => setTitle(event.target.value)} />
                    </label>

                    <label>
                      <span>Mode</span>
                      <select value={mode} onChange={(event) => setMode(event.target.value as TaskMode)}>
                        <option value="agent_command">Mode 3 · Agent Command</option>
                        <option value="agent_delegation">Mode 4 · Agent Delegation</option>
                      </select>
                    </label>

                    <label className="full-span">
                      <span>Natural Language Goal</span>
                      <textarea rows={5} value={userInput} onChange={(event) => setUserInput(event.target.value)} />
                    </label>

                    <label>
                      <span>Max Rounds Per Node</span>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        value={maxRoundsPerNode}
                        onChange={(event) => setMaxRoundsPerNode(Math.max(1, Number(event.target.value) || 1))}
                      />
                    </label>

                    <div className="summary-card">
                      <span className="section-label">Selected Nodes</span>
                      <div className="token-row">
                        {selectedNodes.map((node) => (
                          <span key={node.id} className="token token-static">{node.host_alias}</span>
                        ))}
                      </div>
                      {selectedNodes.length === 0 ? <p className="muted">Pick one or more nodes from the left column.</p> : null}
                    </div>
                  </div>

                  <div className="button-row">
                    <button
                      type="button"
                      onClick={handleCreateTask}
                      disabled={busyAction === "create-task" || selectedNodeIds.length === 0}
                    >
                      {busyAction === "create-task" ? "Initializing..." : "Initialize Task"}
                    </button>
                    {currentTask ? (
                      <button className="secondary" type="button" onClick={() => setIsCreatingTask(false)}>
                        Back to Current Task
                      </button>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {currentMode === "taskspec" && currentTask ? (
                <div className="main-stage">
                  <div className="action-intro">
                    <h3>Approve TaskSpec to begin node work</h3>
                    <p className="muted">
                      This is the only task-level gate. Once approved, the console will start surfacing node proposals one at a time.
                    </p>
                  </div>

                  <label className="full-span">
                    <span>TaskSpec Goal</span>
                    <textarea
                      rows={6}
                      value={goalDraft}
                      onChange={(event) => setGoalDraft(event.target.value)}
                      disabled={!canApproveTaskSpec(currentTask)}
                    />
                  </label>

                  <div className="summary-card">
                    <span className="section-label">What happens next</span>
                    <p>After approval, FleetWarden will wait for node proposals and keep the next pending one in this center panel.</p>
                  </div>

                  <div className="button-row">
                    <button
                      type="button"
                      onClick={handleApproveTaskSpec}
                      disabled={!canApproveTaskSpec(currentTask) || busyAction === "approve-taskspec"}
                    >
                      {busyAction === "approve-taskspec" ? "Approving..." : "Approve TaskSpec"}
                    </button>
                    <button
                      className="secondary"
                      type="button"
                      onClick={handleRejectTaskSpec}
                      disabled={!canRejectTaskSpec(currentTask) || busyAction === "reject-taskspec"}
                    >
                      {busyAction === "reject-taskspec" ? "Rejecting..." : "Reject"}
                    </button>
                  </div>
                </div>
              ) : null}

              {currentMode === "proposal" && activeProposal ? (
                <div className="main-stage proposal-stage">
                  <div className="proposal-head">
                    <div>
                      <h3>{activeProposal.summary}</h3>
                      <p className="muted">
                        {activeProposal.node_label ?? "Unknown node"} · Proposal #{activeProposal.id}
                      </p>
                    </div>
                    <span className={`risk risk-${activeProposal.risk_level}`}>{activeProposal.risk_level}</span>
                  </div>

                  <div className="proposal-grid">
                    <div className="summary-card proposal-content-card">
                      <span className="section-label">Editable Content</span>
                      <pre>{JSON.stringify(activeProposal.editable_content, null, 2)}</pre>
                    </div>

                    <div className="summary-card proposal-context-card">
                      <span className="section-label">Decision Context</span>
                      <CompactList title="Todo Delta" items={activeProposal.todo_delta} />
                      <p><strong>Rationale:</strong> {activeProposal.rationale}</p>
                      <p><strong>Success Hypothesis:</strong> {activeProposal.success_hypothesis}</p>
                      <CompactApprovalList approvals={latestProposal?.approvals ?? []} />
                    </div>
                  </div>

                  <label>
                    <span>Decision Comment</span>
                    <input value={approvalComment} onChange={(event) => setApprovalComment(event.target.value)} />
                  </label>

                  <div className="queue-strip">
                    {currentTaskProposals.map((proposal) => (
                      <button
                        key={proposal.id}
                        type="button"
                        className={`queue-chip ${proposal.id === activeProposal.id ? "queue-chip-active" : ""}`}
                        onClick={() => {
                          if (proposal.task_node_id) {
                            inspectNode(proposal.task_node_id, false);
                          }
                        }}
                      >
                        {proposal.node_label ?? `Proposal ${proposal.id}`}
                      </button>
                    ))}
                  </div>

                  <div className="button-row">
                    <button
                      type="button"
                      onClick={() => handleProposalAction("approve")}
                      disabled={busyAction === `approve-${activeProposal.id}`}
                    >
                      {busyAction === `approve-${activeProposal.id}` ? "Approving..." : "Approve"}
                    </button>
                    <button
                      className="secondary"
                      type="button"
                      onClick={() => handleProposalAction("pause-node")}
                      disabled={busyAction === `pause-node-${activeProposal.id}`}
                    >
                      {busyAction === `pause-node-${activeProposal.id}` ? "Pausing..." : "Pause Node"}
                    </button>
                    <button
                      className="danger"
                      type="button"
                      onClick={() => handleProposalAction("reject")}
                      disabled={busyAction === `reject-${activeProposal.id}`}
                    >
                      {busyAction === `reject-${activeProposal.id}` ? "Rejecting..." : "Reject"}
                    </button>
                  </div>
                </div>
              ) : null}

              {currentMode === "running" && currentTask ? (
                <div className="main-stage">
                  <div className="action-intro">
                    <h3>Task is running</h3>
                    <p className="muted">
                      No user decision is required right now. Keep an eye on the right column for node status changes and the latest execution evidence.
                    </p>
                  </div>

                  <div className="summary-grid">
                    <div className="summary-card">
                      <span className="section-label">Current State</span>
                      <p>{currentTask.status}</p>
                      <p>{Object.keys(nodeStatusCounts).length} node state buckets currently active.</p>
                    </div>
                    <div className="summary-card">
                      <span className="section-label">Next Expected Transition</span>
                      <p>Either a node will emit a fresh proposal, or an executing node will produce a new result.</p>
                    </div>
                  </div>
                </div>
              ) : null}

              {currentMode === "awaiting-proposal" && currentTask ? (
                <div className="main-stage">
                  <div className="action-intro">
                    <h3>Preparing the next proposal</h3>
                    <p className="muted">
                      A node is in <code>awaiting_proposal</code>. The approval buttons will appear here as soon as the worker creates the next proposal.
                    </p>
                  </div>

                  <div className="summary-grid">
                    <div className="summary-card">
                      <span className="section-label">What the system is doing</span>
                      <p>FleetWarden is waiting for the background worker to inspect the node and produce the next proposed action.</p>
                    </div>
                    <div className="summary-card">
                      <span className="section-label">What you can do now</span>
                      <p>Keep this task open, or refresh to check whether the proposal is ready. You can still pause or cancel the task from the right column.</p>
                    </div>
                  </div>

                  <div className="button-row">
                    <button type="button" onClick={() => reloadDashboard(currentTask.id)}>
                      Refresh Status
                    </button>
                  </div>
                </div>
              ) : null}

              {currentMode === "terminal" && currentTask ? (
                <div className="main-stage">
                  <div className="action-intro">
                    <h3>Task finished</h3>
                    <p className="muted">Review outcomes here, then switch tasks or initialize a new one from the top bar.</p>
                  </div>

                  <div className="summary-grid">
                    <div className="summary-card">
                      <span className="section-label">Final Status</span>
                      <p>{currentTask.status}</p>
                    </div>
                    <div className="summary-card">
                      <span className="section-label">Node Outcomes</span>
                      {currentTask.task_nodes.map((taskNode) => (
                        <p key={taskNode.id}>
                          <strong>{taskNode.node.host_alias}:</strong>{" "}
                          {taskNode.success_summary ?? taskNode.failure_summary ?? taskNode.status}
                        </p>
                      ))}
                    </div>
                  </div>
                </div>
              ) : null}

              {!isBooting && !currentTask && currentMode !== "create" ? (
                <div className="empty-state">
                  <h3>No task selected</h3>
                  <p className="muted">Use the top bar to create a new task or switch to an existing one.</p>
                </div>
              ) : null}
            </div>
          </section>
        </section>

        <aside className="column column-right">
          <section className="panel panel-split">
            <div className="panel-header">
              <h2>Progress</h2>
              <div className="button-row">
                <button
                  className="secondary"
                  type="button"
                  onClick={() => handleTaskAction("pause")}
                  disabled={!currentTask || !canPauseTask(currentTask) || busyAction === "pause"}
                >
                  Pause
                </button>
                <button
                  className="secondary"
                  type="button"
                  onClick={() => handleTaskAction("resume")}
                  disabled={!currentTask || !canResumeTask(currentTask) || busyAction === "resume"}
                >
                  Resume
                </button>
                <button
                  className="danger"
                  type="button"
                  onClick={() => handleTaskAction("cancel")}
                  disabled={!currentTask || !canCancelTask(currentTask) || busyAction === "cancel"}
                >
                  Cancel
                </button>
              </div>
            </div>

            <div className="panel-body progress-layout">
              <div className="summary-card">
                <span className="section-label">Node Distribution</span>
                <div className="token-row">
                  {Object.entries(nodeStatusCounts).map(([status, count]) => (
                    <span key={status} className="token token-static">{status}: {count}</span>
                  ))}
                  {Object.keys(nodeStatusCounts).length === 0 ? <span className="muted">No node state yet.</span> : null}
                </div>
              </div>

              <div className="scroll-card progress-list">
                {(currentTask?.task_nodes ?? []).map((taskNode) => (
                  <button
                    key={taskNode.id}
                    type="button"
                    className={`list-row ${inspectedTaskNodeId === taskNode.id ? "list-row-active" : ""}`}
                    onClick={() => inspectNode(taskNode.id, true)}
                  >
                    <div>
                      <strong>{taskNode.node.host_alias}</strong>
                      <span>{taskNode.status}</span>
                    </div>
                    <small>Round {taskNode.current_round}</small>
                  </button>
                ))}
                {!currentTask?.task_nodes.length ? <p className="muted">Task nodes will appear here.</p> : null}
              </div>

              <div className="scroll-card event-list">
                {events.slice(-8).reverse().map((event) => (
                  <article key={event.id} className="event-row">
                    <strong>{event.event_type}</strong>
                    <span>{formatTimestamp(event.created_at)}</span>
                    <small>{JSON.stringify(event.payload)}</small>
                  </article>
                ))}
                {events.length === 0 ? <p className="muted">No events yet.</p> : null}
              </div>
            </div>
          </section>

          <section className="panel panel-split">
            <div className="panel-header">
              <div>
                <h2>Node Inspector</h2>
                <p className="muted">
                  {isNodePinned ? "Pinned to your selected node." : "Following the active proposal automatically."}
                </p>
              </div>
              {isNodePinned ? (
                <button className="secondary" type="button" onClick={() => setIsNodePinned(false)}>
                  Unpin
                </button>
              ) : null}
            </div>

            <div className="panel-body inspector-layout">
              {inspectedTaskNode ? (
                <>
                  <div className="stat-grid compact-stats">
                    <div className="stat">
                      <span>Node</span>
                      <strong>{inspectedTaskNode.node.host_alias}</strong>
                    </div>
                    <div className="stat">
                      <span>Status</span>
                      <strong>{inspectedTaskNode.status}</strong>
                    </div>
                    <div className="stat">
                      <span>Round</span>
                      <strong>{inspectedTaskNode.current_round}</strong>
                    </div>
                    <div className="stat">
                      <span>Last Result</span>
                      <strong>{formatTimestamp(inspectedTaskNode.last_result_at)}</strong>
                    </div>
                  </div>

                  <div className="summary-card inspector-todo-card">
                    <span className="section-label">Current Todo</span>
                    <CompactList title="" items={inspectedTaskNode.agent_state?.todo_items ?? []} hideTitle />
                  </div>

                  <div className="summary-card inspector-proposal-card">
                    <span className="section-label">Latest Proposal</span>
                    <p>{latestProposal?.summary ?? "No proposal yet."}</p>
                  </div>

                  <div className="summary-card">
                    <span className="section-label">Latest Execution</span>
                    <ExecutionSummary result={latestResult} />
                  </div>

                  <div className="scroll-card history-list">
                    {inspectedTaskNode.rounds.map((round) => (
                      <article key={round.id} className="event-row">
                        <strong>Round {round.index}</strong>
                        <span>{round.status}</span>
                        <small>{round.proposals.map((proposal) => proposal.summary).join(" | ") || "No proposal summary"}</small>
                      </article>
                    ))}
                    {inspectedTaskNode.rounds.length === 0 ? <p className="muted">No rounds yet.</p> : null}
                  </div>
                </>
              ) : (
                <div className="empty-state">
                  <h3>No node selected</h3>
                  <p className="muted">Choose a task node from progress or wait for the next proposal to focus one automatically.</p>
                </div>
              )}
            </div>
          </section>
        </aside>
      </section>
    </main>
  );
}

function CompactList({
  title,
  items,
  hideTitle = false,
}: {
  title: string;
  items: string[];
  hideTitle?: boolean;
}) {
  return (
    <div className="mini-list">
      {hideTitle ? null : <span className="section-label">{title}</span>}
      {items.length > 0 ? (
        <ul>
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : (
        <p className="muted">No items.</p>
      )}
    </div>
  );
}

function CompactApprovalList({ approvals }: { approvals: ProposalRecord["approvals"] }) {
  return (
    <div className="mini-list">
      <span className="section-label">Recent Approvals</span>
      {approvals.length > 0 ? (
        <ul>
          {approvals.map((approval) => (
            <li key={approval.id}>
              {approval.decision} by {approval.approved_by}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">No prior approvals on this node yet.</p>
      )}
    </div>
  );
}

function ExecutionSummary({ result }: { result: ExecutionResultRecord | null }) {
  if (!result) {
    return <p>No execution result yet.</p>;
  }

  return (
    <details>
      <summary>{result.execution_summary}</summary>
      {result.stdout ? <pre>{result.stdout}</pre> : null}
      {result.stderr ? <pre>{result.stderr}</pre> : null}
    </details>
  );
}

export default App;
