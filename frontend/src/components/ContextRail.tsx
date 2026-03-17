import { describeEvent, formatTimestamp, truncateText } from "../lib/presenters";
import type {
  ApprovalRecord,
  CurrentMode,
  EventRecord,
  ExecutionResultRecord,
  ProposalRecord,
  RightRailTab,
  TaskNodeRecord,
  TaskRecord,
} from "../types";

type TaskAction = "pause" | "resume" | "cancel";

interface ContextRailProps {
  activeRightTab: RightRailTab;
  busyAction: string | null;
  currentMode: CurrentMode;
  currentTask: TaskRecord | null;
  evidenceApprovals: Array<{ approval: ApprovalRecord; proposal: ProposalRecord }>;
  evidenceResults: Array<{ result: ExecutionResultRecord; proposal: ProposalRecord }>;
  events: EventRecord[];
  inspectedTaskNode: TaskNodeRecord | null;
  inspectedTaskNodeId: number | null;
  isNodePinned: boolean;
  latestProposal: ProposalRecord | null;
  latestResult: ExecutionResultRecord | null;
  nodeStatusCounts: Record<string, number>;
  onInspectNode: (taskNodeId: number, pinned: boolean) => void;
  onOpenEvent: (event: EventRecord) => void;
  onOpenExecution: (result: ExecutionResultRecord, proposalSummary: string | null, nodeLabel: string | null) => void;
  onOpenPayload: (proposal: ProposalRecord, view?: "editable" | "raw") => void;
  onSelectTab: (tab: RightRailTab) => void;
  onTaskAction: (action: TaskAction) => void;
  onUnpin: () => void;
  pauseDisabled: boolean;
  resumeDisabled: boolean;
  cancelDisabled: boolean;
}

export function ContextRail({
  activeRightTab,
  busyAction,
  currentMode,
  currentTask,
  evidenceApprovals,
  evidenceResults,
  events,
  inspectedTaskNode,
  inspectedTaskNodeId,
  isNodePinned,
  latestProposal,
  latestResult,
  nodeStatusCounts,
  onInspectNode,
  onOpenEvent,
  onOpenExecution,
  onOpenPayload,
  onSelectTab,
  onTaskAction,
  onUnpin,
  pauseDisabled,
  resumeDisabled,
  cancelDisabled,
}: ContextRailProps) {
  return (
    <aside className="column column-right">
      <section className="panel rail-panel">
        <div className="panel-header">
          <h2>Context Rail</h2>
          <div className="button-row compact-actions">
            <button className="secondary" type="button" onClick={() => onTaskAction("pause")} disabled={pauseDisabled}>
              {busyAction === "pause" ? "Pausing..." : "Pause"}
            </button>
            <button className="secondary" type="button" onClick={() => onTaskAction("resume")} disabled={resumeDisabled}>
              {busyAction === "resume" ? "Resuming..." : "Resume"}
            </button>
            <button className="danger" type="button" onClick={() => onTaskAction("cancel")} disabled={cancelDisabled}>
              {busyAction === "cancel" ? "Cancelling..." : "Cancel"}
            </button>
          </div>
        </div>

        <div className="panel-body rail-layout">
          <div className="tab-strip">
            {(["progress", "inspector", "evidence"] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                className={`tab-chip ${activeRightTab === tab ? "tab-chip-active" : ""}`}
                onClick={() => onSelectTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>

          {activeRightTab === "progress" ? (
            <div className="rail-content">
              <div className="summary-card">
                <span className="section-label">Node Distribution</span>
                <div className="token-row">
                  {Object.entries(nodeStatusCounts).map(([status, count]) => (
                    <span key={status} className="token token-static">
                      {status}: {count}
                    </span>
                  ))}
                  {Object.keys(nodeStatusCounts).length === 0 ? <span className="muted">No node state yet.</span> : null}
                </div>
              </div>

              <div className="summary-card scroll-card">
                <span className="section-label">Nodes</span>
                <div className="rail-scroll-list">
                  {(currentTask?.task_nodes ?? []).map((taskNode) => (
                    <button
                      key={taskNode.id}
                      type="button"
                      className={`list-row ${inspectedTaskNodeId === taskNode.id ? "list-row-active" : ""}`}
                      onClick={() => {
                        onInspectNode(taskNode.id, true);
                        onSelectTab("inspector");
                      }}
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
              </div>

              <div className="summary-card scroll-card">
                <span className="section-label">Recent Events</span>
                <div className="rail-scroll-list">
                  {events.slice(-5).reverse().map((event) => (
                    <article key={event.id} className="event-row">
                      <strong>{event.event_type}</strong>
                      <span>{formatTimestamp(event.created_at)}</span>
                      <small>{describeEvent(event)}</small>
                      <button className="secondary" type="button" onClick={() => onOpenEvent(event)}>
                        Open
                      </button>
                    </article>
                  ))}
                  {events.length === 0 ? <p className="muted">No events yet.</p> : null}
                </div>
              </div>
            </div>
          ) : null}

          {activeRightTab === "inspector" ? (
            <div className="rail-content">
              {inspectedTaskNode ? (
                <>
                  <div className="panel-header compact-header">
                    <div>
                      <span className="section-label">Node Focus</span>
                      <h3>{inspectedTaskNode.node.host_alias}</h3>
                    </div>
                    {isNodePinned ? (
                      <button className="secondary" type="button" onClick={onUnpin}>
                        Unpin
                      </button>
                    ) : null}
                  </div>

                  <div className="stat-grid compact-stats">
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
                    <div className="stat">
                      <span>Todo Items</span>
                      <strong>{inspectedTaskNode.agent_state?.todo_items.length ?? 0}</strong>
                    </div>
                  </div>

                  <div className="summary-card">
                    <span className="section-label">Current Todo</span>
                    <ul className="mini-list">
                      {(inspectedTaskNode.agent_state?.todo_items ?? []).slice(0, 3).map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                    {(inspectedTaskNode.agent_state?.todo_items.length ?? 0) > 3 ? (
                      <p className="muted">More todo items are available in the full node history.</p>
                    ) : null}
                  </div>

                  <div className="summary-card">
                    <span className="section-label">Latest Proposal</span>
                    <p className="clamp-2">{truncateText(latestProposal?.summary ?? "No proposal yet.", 140)}</p>
                    {latestProposal ? (
                      <button className="secondary" type="button" onClick={() => onOpenPayload(latestProposal, "editable")}>
                        View Full Payload
                      </button>
                    ) : null}
                  </div>

                  <div className="summary-card">
                    <span className="section-label">Latest Execution</span>
                    <p className="clamp-2">{truncateText(latestResult?.execution_summary ?? "No execution result yet.", 140)}</p>
                    {latestResult ? (
                      <button
                        className="secondary"
                        type="button"
                        onClick={() => onOpenExecution(latestResult, latestProposal?.summary ?? null, inspectedTaskNode.node.host_alias)}
                      >
                        View Full Output
                      </button>
                    ) : null}
                  </div>
                </>
              ) : (
                <div className="empty-state">
                  <h3>No node selected</h3>
                  <p className="muted">Choose a node from Progress or wait for the next proposal to focus one automatically.</p>
                </div>
              )}
            </div>
          ) : null}

          {activeRightTab === "evidence" ? (
            <div className="rail-content">
              <div className="summary-card scroll-card">
                <span className="section-label">Execution Results</span>
                <div className="rail-scroll-list">
                  {evidenceResults.map(({ result, proposal }) => (
                    <article key={result.id} className="event-row">
                      <strong>{truncateText(result.execution_summary, 80)}</strong>
                      <small>{truncateText(proposal.summary, 90)}</small>
                      <button
                        className="secondary"
                        type="button"
                        onClick={() => onOpenExecution(result, proposal.summary, proposal.node_label)}
                      >
                        Open
                      </button>
                    </article>
                  ))}
                  {evidenceResults.length === 0 ? <p className="muted">No execution evidence for the current node yet.</p> : null}
                </div>
              </div>

              <div className="summary-card scroll-card">
                <span className="section-label">Approvals</span>
                <div className="rail-scroll-list">
                  {evidenceApprovals.map(({ approval, proposal }) => (
                    <article key={approval.id} className="event-row">
                      <strong>{approval.decision} by {approval.approved_by}</strong>
                      <small>{truncateText(proposal.summary, 100)}</small>
                      <button className="secondary" type="button" onClick={() => onOpenPayload(proposal, "editable")}>
                        Payload
                      </button>
                    </article>
                  ))}
                  {evidenceApprovals.length === 0 ? <p className="muted">No approval evidence for the current node yet.</p> : null}
                </div>
              </div>

              <div className="summary-card scroll-card">
                <span className="section-label">Event Payloads</span>
                <div className="rail-scroll-list">
                  {events.slice(-5).reverse().map((event) => (
                    <article key={event.id} className="event-row">
                      <strong>{event.event_type}</strong>
                      <small>{truncateText(JSON.stringify(event.payload), 100)}</small>
                      <button className="secondary" type="button" onClick={() => onOpenEvent(event)}>
                        Open
                      </button>
                    </article>
                  ))}
                  {events.length === 0 ? <p className="muted">No event evidence yet.</p> : null}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </section>
    </aside>
  );
}
