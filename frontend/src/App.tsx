import { useEffect, useMemo, useRef, useState } from "react";

import "./styles.css";
import { ActionConsole } from "./components/ActionConsole";
import { ContextRail } from "./components/ContextRail";
import { CreateTaskWorkspace } from "./components/CreateTaskWorkspace";
import { DetailDrawer } from "./components/DetailDrawer";
import { NodeSelectionRail } from "./components/NodeSelectionRail";
import { TaskSummaryRail } from "./components/TaskSummaryRail";
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
import { getDefaultRightRailTab } from "./lib/presenters";
import type {
  ApprovalRecord,
  CurrentMode,
  DetailDrawerState,
  EventRecord,
  ExecutionResultRecord,
  NodeRecord,
  ProposalRecord,
  RightRailTab,
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

function getProposalHistory(taskNode: TaskNodeRecord | null): ProposalRecord[] {
  return taskNode?.rounds.flatMap((round) => round.proposals) ?? [];
}

function getLatestApproval(proposals: ProposalRecord[]): ApprovalRecord | null {
  return proposals.flatMap((proposal) => proposal.approvals).at(-1) ?? null;
}

function getLatestExecutionResult(proposals: ProposalRecord[]): ExecutionResultRecord | null {
  return proposals.flatMap((proposal) => proposal.execution_results).at(-1) ?? null;
}

function sortTasksByNewestCreated(tasks: TaskRecord[]): TaskRecord[] {
  return [...tasks].sort((left, right) => {
    const rightCreatedAt = Date.parse(right.created_at);
    const leftCreatedAt = Date.parse(left.created_at);

    if (rightCreatedAt !== leftCreatedAt) {
      return rightCreatedAt - leftCreatedAt;
    }

    return right.id - left.id;
  });
}

function App() {
  const currentTaskIdRef = useRef<number | null>(null);
  const previousTaskIdRef = useRef<number | null>(null);
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
  const [activeProposalNode, setActiveProposalNode] = useState<TaskNodeRecord | null>(null);
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
  const [activeRightTab, setActiveRightTab] = useState<RightRailTab>("progress");
  const [isRightTabManuallySelected, setIsRightTabManuallySelected] = useState(false);
  const [detailDrawer, setDetailDrawer] = useState<DetailDrawerState | null>(null);

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

      const sortedTasks = sortTasksByNewestCreated(taskData);

      setNodes(nodeData);
      setTasks(sortedTasks);
      setPendingProposals(proposalData);

      const preferredSelection = preferredTaskId ?? currentTaskIdRef.current;
      const selectedTaskStillExists = preferredSelection
        ? sortedTasks.some((task) => task.id === preferredSelection)
        : false;
      const nextTaskId = selectedTaskStillExists ? preferredSelection : sortedTasks[0]?.id ?? null;

      if (nextTaskId) {
        const task = await fetchTask(nextTaskId);
        if (reloadSequenceRef.current !== reloadId) {
          return;
        }
        currentTaskIdRef.current = task.id;
        setCurrentTaskId(task.id);
        setCurrentTask(task);
      } else {
        currentTaskIdRef.current = null;
        setCurrentTaskId(null);
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
    fetchTaskEvents(currentTaskId).then((data) => setEvents(data.slice(-12))).catch(() => undefined);
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

  useEffect(
    () =>
      connectEvents("/proposals/events", () => {
        reloadDashboard(currentTaskId).catch(() => undefined);
      }),
    [currentTaskId]
  );

  const currentTaskProposals = useMemo(
    () => pendingProposals.filter((proposal) => proposal.task_id === currentTaskId),
    [currentTaskId, pendingProposals]
  );

  const activeProposal = currentTaskProposals[0] ?? null;

  useEffect(() => {
    const activeProposalTaskNodeId = activeProposal?.task_node_id;
    if (!activeProposalTaskNodeId) {
      setActiveProposalNode(null);
      return;
    }
    fetchTaskNode(activeProposalTaskNodeId).then(setActiveProposalNode).catch(() => undefined);
  }, [activeProposal?.id, activeProposal?.task_node_id]);

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

  const summaryCounts = useMemo(
    () =>
      tasks.reduce(
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
      ),
    [tasks]
  );

  const nodeStatusCounts = useMemo(
    () =>
      (currentTask?.task_nodes ?? []).reduce<Record<string, number>>((accumulator, taskNode) => {
        accumulator[taskNode.status] = (accumulator[taskNode.status] ?? 0) + 1;
        return accumulator;
      }, {}),
    [currentTask?.task_nodes]
  );

  const hasAwaitingProposalNode = useMemo(
    () => (currentTask?.task_nodes ?? []).some((taskNode) => taskNode.status === "awaiting_proposal"),
    [currentTask?.task_nodes]
  );

  const currentMode = useMemo<CurrentMode>(() => {
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

  useEffect(() => {
    const defaultTab = getDefaultRightRailTab(currentMode);
    const taskChanged = previousTaskIdRef.current !== currentTaskId;

    if (taskChanged) {
      previousTaskIdRef.current = currentTaskId;
      setActiveRightTab(defaultTab);
      setIsRightTabManuallySelected(false);
      setDetailDrawer(null);
      return;
    }

    if (!isRightTabManuallySelected) {
      setActiveRightTab(defaultTab);
    }
  }, [currentMode, currentTaskId, isRightTabManuallySelected]);

  const activeProposalHistory = useMemo(() => getProposalHistory(activeProposalNode), [activeProposalNode]);
  const activeProposalLatestApproval = useMemo(() => getLatestApproval(activeProposalHistory), [activeProposalHistory]);
  const activeProposalLatestResult = useMemo(() => getLatestExecutionResult(activeProposalHistory), [activeProposalHistory]);

  const inspectedProposalHistory = useMemo(() => getProposalHistory(inspectedTaskNode), [inspectedTaskNode]);
  const latestProposal = inspectedProposalHistory.at(-1) ?? null;
  const latestResult = useMemo(() => getLatestExecutionResult(inspectedProposalHistory), [inspectedProposalHistory]);
  const evidenceResults = useMemo(
    () =>
      inspectedProposalHistory
        .flatMap((proposal) => proposal.execution_results.map((result) => ({ result, proposal })))
        .slice(-4)
        .reverse(),
    [inspectedProposalHistory]
  );
  const evidenceApprovals = useMemo(
    () =>
      inspectedProposalHistory
        .flatMap((proposal) => proposal.approvals.map((approval) => ({ approval, proposal })))
        .slice(-4)
        .reverse(),
    [inspectedProposalHistory]
  );

  const toggleNode = (nodeId: number) => {
    setSelectedNodeIds((current) => (current.includes(nodeId) ? current.filter((id) => id !== nodeId) : [...current, nodeId]));
  };

  const handleSelectTask = (taskId: number | null) => {
    setIsCreatingTask(false);
    currentTaskIdRef.current = taskId;
    setCurrentTaskId(taskId);
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
      currentTaskIdRef.current = task.id;
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

  const handleTaskAction = async (action: "pause" | "resume" | "cancel") => {
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
    setDetailDrawer(null);
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

  const openTaskSpecDrawer = () => {
    if (!currentTaskSpec) {
      return;
    }
    setDetailDrawer({
      kind: "taskspec",
      sourceId: currentTaskSpec.id,
      taskSpec: currentTaskSpec,
    });
  };

  const openPayloadDrawer = (proposal: ProposalRecord, view: "editable" | "raw" = "editable") => {
    setDetailDrawer({
      kind: "payload",
      sourceId: proposal.id,
      proposal,
      view,
    });
  };

  const openExecutionDrawer = (
    executionResult: ExecutionResultRecord,
    proposalSummary: string | null,
    nodeLabel: string | null
  ) => {
    setDetailDrawer({
      kind: "execution",
      sourceId: executionResult.id,
      executionResult,
      proposalSummary,
      nodeLabel,
    });
  };

  const openEventDrawer = (event: EventRecord) => {
    setDetailDrawer({
      kind: "event",
      sourceId: event.id,
      event,
    });
  };

  const handlePayloadViewChange = (view: "editable" | "raw") => {
    setDetailDrawer((current) => (current?.kind === "payload" ? { ...current, view } : current));
  };

  const pauseDisabled = !currentTask || !canPauseTask(currentTask) || busyAction === "pause";
  const resumeDisabled = !currentTask || !canResumeTask(currentTask) || busyAction === "resume";
  const cancelDisabled = !currentTask || !canCancelTask(currentTask) || busyAction === "cancel";

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
                handleSelectTask(rawValue ? Number(rawValue) : null);
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

      <section className={`workspace-grid ${currentMode === "create" ? "workspace-grid-create" : ""}`}>
        <aside className="column">
          {currentMode === "create" ? (
            <NodeSelectionRail
              filteredNodes={filteredNodes}
              isRefreshingNodes={isRefreshingNodes}
              nodeQuery={nodeQuery}
              onNodeQueryChange={setNodeQuery}
              onRefreshNodes={handleRefreshNodes}
              onToggleNode={toggleNode}
              selectedNodeIds={selectedNodeIds}
              selectedNodes={selectedNodes}
            />
          ) : (
            <TaskSummaryRail
              currentMode={currentMode}
              task={currentTask}
              taskSpec={currentTaskSpec}
              onOpenTaskSpec={openTaskSpecDrawer}
            />
          )}
        </aside>

        <section className="column">
          {currentMode === "create" ? (
            <CreateTaskWorkspace
              busyAction={busyAction}
              currentTaskExists={Boolean(currentTask)}
              maxRoundsPerNode={maxRoundsPerNode}
              mode={mode}
              onCreateTask={handleCreateTask}
              onMaxRoundsChange={setMaxRoundsPerNode}
              onModeChange={setMode}
              onReturnToTask={() => setIsCreatingTask(false)}
              onTitleChange={setTitle}
              onUserInputChange={setUserInput}
              selectedNodeIds={selectedNodeIds}
              selectedNodes={selectedNodes}
              title={title}
              userInput={userInput}
            />
          ) : (
            <ActionConsole
              approvalComment={approvalComment}
              busyAction={busyAction}
              canApproveTaskSpecAction={Boolean(currentTask && canApproveTaskSpec(currentTask))}
              canRejectTaskSpecAction={Boolean(currentTask && canRejectTaskSpec(currentTask))}
              currentMode={currentMode}
              currentTask={currentTask}
              currentTaskProposals={currentTaskProposals}
              currentTaskSpec={currentTaskSpec}
              activeProposal={activeProposal}
              activeProposalLatestApproval={activeProposalLatestApproval}
              activeProposalLatestResult={activeProposalLatestResult}
              goalDraft={goalDraft}
              nodeLabel={activeProposalNode?.node.host_alias ?? activeProposal?.node_label ?? null}
              onApprovalCommentChange={setApprovalComment}
              onApproveProposal={() => handleProposalAction("approve")}
              onApproveTaskSpec={handleApproveTaskSpec}
              onGoalDraftChange={setGoalDraft}
              onOpenPayload={openPayloadDrawer}
              onOpenTaskSpec={openTaskSpecDrawer}
              onPauseProposalNode={() => handleProposalAction("pause-node")}
              onRefreshAwaitingProposal={() => {
                if (currentTask) {
                  reloadDashboard(currentTask.id).catch(() => undefined);
                }
              }}
              onRejectProposal={() => handleProposalAction("reject")}
              onRejectTaskSpec={handleRejectTaskSpec}
            />
          )}
        </section>

        {currentMode !== "create" ? (
          <ContextRail
            activeRightTab={activeRightTab}
            busyAction={busyAction}
            cancelDisabled={cancelDisabled}
            currentMode={currentMode}
            currentTask={currentTask}
            evidenceApprovals={evidenceApprovals}
            evidenceResults={evidenceResults}
            events={events}
            inspectedTaskNode={inspectedTaskNode}
            inspectedTaskNodeId={inspectedTaskNodeId}
            isNodePinned={isNodePinned}
            latestProposal={latestProposal}
            latestResult={latestResult}
            nodeStatusCounts={nodeStatusCounts}
            onInspectNode={inspectNode}
            onOpenEvent={openEventDrawer}
            onOpenExecution={openExecutionDrawer}
            onOpenPayload={openPayloadDrawer}
            onSelectTab={(tab) => {
              setActiveRightTab(tab);
              setIsRightTabManuallySelected(true);
            }}
            onTaskAction={handleTaskAction}
            onUnpin={() => setIsNodePinned(false)}
            pauseDisabled={pauseDisabled}
            resumeDisabled={resumeDisabled}
          />
        ) : null}
      </section>

      <DetailDrawer
        drawer={detailDrawer}
        onClose={() => setDetailDrawer(null)}
        onPayloadViewChange={handlePayloadViewChange}
      />

      {!isBooting && !currentTask && currentMode !== "create" ? (
        <div className="error-banner">No task is selected yet. Start a task or switch to one from the top bar.</div>
      ) : null}
    </main>
  );
}

export default App;
