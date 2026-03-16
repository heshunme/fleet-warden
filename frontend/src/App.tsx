import { useEffect, useState } from "react";

import "./styles.css";
import {
  buildApiUrl,
  fetchNodes,
  fetchPendingProposals,
  fetchTask,
  fetchTaskNode,
  fetchTasks,
} from "./lib/api";
import { ApprovalQueue } from "./pages/ApprovalQueue";
import { NodeDetailPage } from "./pages/NodeDetailPage";
import { TaskCreatePage } from "./pages/TaskCreatePage";
import { TaskOverviewPage } from "./pages/TaskOverviewPage";
import { TaskSpecPage } from "./pages/TaskSpecPage";
import type { EventRecord, NodeRecord, ProposalRecord, TaskNodeRecord, TaskRecord } from "./types";

function connectTaskEvents(taskId: number, onEvent: (event: EventRecord) => void) {
  const source = new EventSource(buildApiUrl(`/tasks/${taskId}/events`));
  source.onmessage = (event) => {
    onEvent(JSON.parse(event.data) as EventRecord);
  };
  return () => source.close();
}

export default function App() {
  const [nodes, setNodes] = useState<NodeRecord[]>([]);
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [selectedTask, setSelectedTask] = useState<TaskRecord | null>(null);
  const [selectedTaskNode, setSelectedTaskNode] = useState<TaskNodeRecord | null>(null);
  const [pendingProposals, setPendingProposals] = useState<ProposalRecord[]>([]);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reloadDashboard = async (taskId?: number) => {
    try {
      const [nodeData, taskData, proposalData] = await Promise.all([
        fetchNodes(),
        fetchTasks(),
        fetchPendingProposals(),
      ]);
      setNodes(nodeData);
      setTasks(taskData);
      setPendingProposals(proposalData);
      const effectiveTaskId = taskId ?? selectedTask?.id ?? taskData[0]?.id;
      if (effectiveTaskId) {
        const task = await fetchTask(effectiveTaskId);
        setSelectedTask(task);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unknown error");
    }
  };

  useEffect(() => {
    reloadDashboard().catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!selectedTask) {
      return undefined;
    }
    return connectTaskEvents(selectedTask.id, (event) => {
      setEvents((current) => [...current.slice(-24), event]);
      fetchTask(selectedTask.id).then(setSelectedTask);
      fetchPendingProposals().then(setPendingProposals);
    });
  }, [selectedTask?.id]);

  const handleTaskCreated = async (task: TaskRecord) => {
    setSelectedTask(task);
    await reloadDashboard(task.id);
  };

  const handleTaskUpdated = async (task: TaskRecord) => {
    setSelectedTask(task);
    await reloadDashboard(task.id);
  };

  const handleSelectTaskNode = async (taskNodeId: number) => {
    const taskNode = await fetchTaskNode(taskNodeId);
    setSelectedTaskNode(taskNode);
  };

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">FleetWarden</p>
          <h1>SSH-first AI operations control plane</h1>
          <p className="hero-copy">
            Create a task, approve the TaskSpec, review per-node proposals, and track execution with auditable state.
          </p>
        </div>
        <aside className="hero-sidebar">
          <h2>Recent Tasks</h2>
          <div className="task-pills">
            {tasks.map((task) => (
              <button key={task.id} className="pill" onClick={() => setSelectedTask(task)} type="button">
                #{task.id} {task.title}
              </button>
            ))}
          </div>
        </aside>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      <div className="layout">
        <TaskCreatePage nodes={nodes} onNodesUpdated={setNodes} onTaskCreated={handleTaskCreated} />
        <TaskSpecPage task={selectedTask} onTaskUpdated={handleTaskUpdated} />
        <TaskOverviewPage
          task={selectedTask}
          events={events}
          onTaskUpdated={handleTaskUpdated}
          onSelectTaskNode={handleSelectTaskNode}
        />
        <NodeDetailPage taskNode={selectedTaskNode} />
        <ApprovalQueue proposals={pendingProposals} onProposalHandled={() => reloadDashboard(selectedTask?.id)} />
      </div>
    </main>
  );
}
