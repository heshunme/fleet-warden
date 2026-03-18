import { useMemo, useState } from "react";

import { createTask, refreshNodes } from "../lib/api";
import type { NodeRecord, TaskMode, TaskRecord } from "../types";
import { SectionCard } from "../components/SectionCard";

interface TaskCreatePageProps {
  nodes: NodeRecord[];
  onNodesUpdated: (nodes: NodeRecord[]) => void;
  onTaskCreated: (task: TaskRecord) => void;
}

export function TaskCreatePage({ nodes, onNodesUpdated, onTaskCreated }: TaskCreatePageProps) {
  const [query, setQuery] = useState("");
  const [selectedNodeIds, setSelectedNodeIds] = useState<number[]>([]);
  const [mode, setMode] = useState<TaskMode>("agent_command");
  const [userInput, setUserInput] = useState("Inspect current node state and report back the next safe action.");
  const [submitting, setSubmitting] = useState(false);

  const filteredNodes = useMemo(
    () =>
      nodes.filter((node) =>
        [node.name, node.host_alias, node.hostname].join(" ").toLowerCase().includes(query.toLowerCase())
      ),
    [nodes, query]
  );

  const toggleNode = (nodeId: number) => {
    setSelectedNodeIds((current) =>
      current.includes(nodeId) ? current.filter((id) => id !== nodeId) : [...current, nodeId]
    );
  };

  const handleRefresh = async () => {
    const refreshed = await refreshNodes();
    onNodesUpdated(refreshed);
  };

  const handleCreate = async () => {
    setSubmitting(true);
    try {
      const task = await createTask({
        mode,
        user_input: userInput,
        node_ids: selectedNodeIds,
        max_rounds_per_node: 3,
      });
      onTaskCreated(task);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SectionCard
      title="Task Creation"
      action={
        <button className="secondary" onClick={handleRefresh} type="button">
          Refresh SSH Nodes
        </button>
      }
    >
      <div className="grid-two">
        <div className="stack">
          <label>
            <span>Mode</span>
            <select value={mode} onChange={(event) => setMode(event.target.value as TaskMode)}>
              <option value="agent_command">Mode 3 · Agent Command</option>
              <option value="agent_delegation">Mode 4 · Agent Delegation</option>
            </select>
          </label>
          <label>
            <span>Natural Language Goal</span>
            <textarea rows={6} value={userInput} onChange={(event) => setUserInput(event.target.value)} />
          </label>
          <button onClick={handleCreate} type="button" disabled={submitting || selectedNodeIds.length === 0}>
            {submitting ? "Initializing..." : "Initialize Task"}
          </button>
        </div>
        <div className="stack">
          <label>
            <span>Search Nodes</span>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="host, alias, hostname" />
          </label>
          <div className="node-list">
            {filteredNodes.map((node) => (
              <label key={node.id} className="node-row">
                <input
                  type="checkbox"
                  checked={selectedNodeIds.includes(node.id)}
                  onChange={() => toggleNode(node.id)}
                />
                <div>
                  <strong>{node.host_alias}</strong>
                  <span>{node.username ?? "root"}@{node.hostname}:{node.port}</span>
                  {node.capability_warnings.length > 0 ? (
                    <small>{node.capability_warnings.join(", ")}</small>
                  ) : null}
                </div>
              </label>
            ))}
            {filteredNodes.length === 0 ? <p className="muted">No nodes discovered yet.</p> : null}
          </div>
        </div>
      </div>
    </SectionCard>
  );
}
