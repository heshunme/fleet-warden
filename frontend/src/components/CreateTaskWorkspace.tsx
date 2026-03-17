import type { NodeRecord, TaskMode } from "../types";

interface CreateTaskWorkspaceProps {
  busyAction: string | null;
  currentTaskExists: boolean;
  maxRoundsPerNode: number;
  mode: TaskMode;
  selectedNodeIds: number[];
  selectedNodes: NodeRecord[];
  title: string;
  userInput: string;
  onCreateTask: () => void;
  onMaxRoundsChange: (value: number) => void;
  onModeChange: (value: TaskMode) => void;
  onReturnToTask: () => void;
  onTitleChange: (value: string) => void;
  onUserInputChange: (value: string) => void;
}

export function CreateTaskWorkspace({
  busyAction,
  currentTaskExists,
  maxRoundsPerNode,
  mode,
  selectedNodeIds,
  selectedNodes,
  title,
  userInput,
  onCreateTask,
  onMaxRoundsChange,
  onModeChange,
  onReturnToTask,
  onTitleChange,
  onUserInputChange,
}: CreateTaskWorkspaceProps) {
  return (
    <section className="panel main-panel">
      <div className="panel-header">
        <div>
          <h2>Initialize Task</h2>
          <p className="muted">Creation gets a larger two-column layout so node selection and task definition both stay readable.</p>
        </div>
      </div>

      <div className="panel-body create-layout">
        <div className="summary-card">
          <span className="section-label">Task Setup</span>
          <p>The console returns to the normal single-screen workflow immediately after task creation.</p>
        </div>

        <div className="form-grid">
          <label>
            <span>Title</span>
            <input value={title} onChange={(event) => onTitleChange(event.target.value)} />
          </label>

          <label>
            <span>Mode</span>
            <select value={mode} onChange={(event) => onModeChange(event.target.value as TaskMode)}>
              <option value="agent_command">Mode 3 · Agent Command</option>
              <option value="agent_delegation">Mode 4 · Agent Delegation</option>
            </select>
          </label>

          <label className="full-span">
            <span>Natural Language Goal</span>
            <textarea rows={6} value={userInput} onChange={(event) => onUserInputChange(event.target.value)} />
          </label>

          <label>
            <span>Max Rounds Per Node</span>
            <input
              type="number"
              min={1}
              max={10}
              value={maxRoundsPerNode}
              onChange={(event) => onMaxRoundsChange(Math.max(1, Number(event.target.value) || 1))}
            />
          </label>

          <div className="summary-card">
            <span className="section-label">Selected Nodes</span>
            <div className="token-row">
              {selectedNodes.map((node) => (
                <span key={node.id} className="token token-static">
                  {node.host_alias}
                </span>
              ))}
            </div>
            {selectedNodes.length === 0 ? <p className="muted">Pick one or more nodes from the left rail.</p> : null}
          </div>
        </div>

        <div className="button-row">
          <button type="button" onClick={onCreateTask} disabled={busyAction === "create-task" || selectedNodeIds.length === 0}>
            {busyAction === "create-task" ? "Initializing..." : "Initialize Task"}
          </button>
          {currentTaskExists ? (
            <button className="secondary" type="button" onClick={onReturnToTask}>
              Back to Current Task
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
