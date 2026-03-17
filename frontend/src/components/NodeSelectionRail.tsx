import type { NodeRecord } from "../types";

interface NodeSelectionRailProps {
  filteredNodes: NodeRecord[];
  isRefreshingNodes: boolean;
  nodeQuery: string;
  onNodeQueryChange: (value: string) => void;
  onRefreshNodes: () => void;
  onToggleNode: (nodeId: number) => void;
  onRemoveNode: (nodeId: number) => void;
  selectedNodeIds: number[];
  selectedNodes: NodeRecord[];
}

export function NodeSelectionRail({
  filteredNodes,
  isRefreshingNodes,
  nodeQuery,
  onNodeQueryChange,
  onRefreshNodes,
  onRemoveNode,
  onToggleNode,
  selectedNodeIds,
  selectedNodes,
}: NodeSelectionRailProps) {
  const selectedNodeSummary =
    selectedNodes.length > 0
      ? `${selectedNodes.length} node${selectedNodes.length === 1 ? "" : "s"} selected`
      : "Choose at least one node to initialize a task.";

  return (
    <section className="panel rail-panel">
      <div className="panel-header">
        <div>
          <h2>Node Selection</h2>
          <p className="muted">Search, pick, and prune target nodes before you initialize a new task.</p>
        </div>
        <button className="secondary" type="button" onClick={onRefreshNodes} disabled={isRefreshingNodes}>
          {isRefreshingNodes ? "Refreshing..." : "Refresh SSH Nodes"}
        </button>
      </div>

      <div className="panel-body rail-layout">
        <label>
          <span>Search Nodes</span>
          <input
            value={nodeQuery}
            onChange={(event) => onNodeQueryChange(event.target.value)}
            placeholder="host, alias, hostname"
          />
        </label>

        <div className="summary-card">
          <span className="section-label">Selection</span>
          <strong>{selectedNodeSummary}</strong>
          <div className="token-row">
            {selectedNodes.map((node) => (
              <button key={node.id} type="button" className="token" onClick={() => onRemoveNode(node.id)}>
                {node.host_alias}
              </button>
            ))}
          </div>
        </div>

        <div className="scroll-card rail-scroll-list">
          {filteredNodes.map((node) => {
            const selected = selectedNodeIds.includes(node.id);
            return (
              <button
                key={node.id}
                type="button"
                className={`list-row ${selected ? "list-row-active" : ""}`}
                onClick={() => onToggleNode(node.id)}
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
  );
}
