import {
  buildEditableContentPreview,
  buildTaskSpecCounters,
  summarizeProposalContext,
  summarizeTask,
  truncateText,
} from "../lib/presenters";
import type {
  ApprovalRecord,
  CurrentMode,
  ExecutionResultRecord,
  ProposalRecord,
  TaskRecord,
  TaskSpecRecord,
} from "../types";

interface ActionConsoleProps {
  approvalComment: string;
  busyAction: string | null;
  canApproveTaskSpecAction: boolean;
  canRejectTaskSpecAction: boolean;
  currentMode: CurrentMode;
  currentTask: TaskRecord | null;
  currentTaskProposals: ProposalRecord[];
  currentTaskSpec: TaskSpecRecord | null;
  activeProposal: ProposalRecord | null;
  activeProposalLatestApproval: ApprovalRecord | null;
  activeProposalLatestResult: ExecutionResultRecord | null;
  goalDraft: string;
  nodeLabel: string | null;
  onApprovalCommentChange: (value: string) => void;
  onApproveProposal: () => void;
  onApproveTaskSpec: () => void;
  onGoalDraftChange: (value: string) => void;
  onOpenPayload: (proposal: ProposalRecord, view?: "editable" | "raw") => void;
  onOpenTaskSpec: () => void;
  onPauseProposalNode: () => void;
  onRefreshAwaitingProposal: () => void;
  onRejectProposal: () => void;
  onRejectTaskSpec: () => void;
}

export function ActionConsole({
  approvalComment,
  busyAction,
  canApproveTaskSpecAction,
  canRejectTaskSpecAction,
  currentMode,
  currentTask,
  currentTaskProposals,
  currentTaskSpec,
  activeProposal,
  activeProposalLatestApproval,
  activeProposalLatestResult,
  goalDraft,
  nodeLabel,
  onApprovalCommentChange,
  onApproveProposal,
  onApproveTaskSpec,
  onGoalDraftChange,
  onOpenPayload,
  onOpenTaskSpec,
  onPauseProposalNode,
  onRefreshAwaitingProposal,
  onRejectProposal,
  onRejectTaskSpec,
}: ActionConsoleProps) {
  const taskSpecCounters = buildTaskSpecCounters(currentTaskSpec);
  const previewModel = activeProposal ? buildEditableContentPreview(activeProposal.editable_content) : null;
  const proposalContext = activeProposal ? summarizeProposalContext(activeProposal) : null;

  return (
    <section className="panel main-panel">
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
        {currentMode === "taskspec" && currentTask ? (
          <div className="main-stage">
            <div className="action-intro">
              <h3>Approve TaskSpec to begin node work</h3>
              <p className="muted">Keep the edit surface focused on the goal, and push the full TaskSpec into the detail drawer.</p>
            </div>

            <div className="token-row">
              {taskSpecCounters.map((counter) => (
                <span key={counter.label} className="token token-static count-token">
                  {counter.label} {counter.count}
                </span>
              ))}
            </div>

            <label className="full-span">
              <span>TaskSpec Goal</span>
              <textarea
                rows={8}
                value={goalDraft}
                onChange={(event) => onGoalDraftChange(event.target.value)}
                disabled={!canApproveTaskSpecAction}
              />
            </label>

            <div className="summary-card">
              <span className="section-label">What happens next</span>
              <p>Once approved, FleetWarden will move this center stage to the next pending proposal automatically.</p>
            </div>

            <div className="button-row">
              <button
                type="button"
                onClick={onApproveTaskSpec}
                disabled={!canApproveTaskSpecAction || busyAction === "approve-taskspec"}
              >
                {busyAction === "approve-taskspec" ? "Approving..." : "Approve TaskSpec"}
              </button>
              <button
                className="secondary"
                type="button"
                onClick={onRejectTaskSpec}
                disabled={!canRejectTaskSpecAction || busyAction === "reject-taskspec"}
              >
                {busyAction === "reject-taskspec" ? "Rejecting..." : "Reject"}
              </button>
              <button className="secondary" type="button" onClick={onOpenTaskSpec} disabled={!currentTaskSpec}>
                View Full TaskSpec
              </button>
            </div>
          </div>
        ) : null}

        {currentMode === "proposal" && activeProposal && previewModel && proposalContext ? (
          <div className="main-stage proposal-stage">
            <div className="proposal-head">
              <div>
                <h3>{activeProposal.summary}</h3>
                <p className="muted">{nodeLabel ?? activeProposal.node_label ?? "Unknown node"} · Proposal #{activeProposal.id}</p>
              </div>
              <span className={`risk risk-${activeProposal.risk_level}`}>{activeProposal.risk_level}</span>
            </div>

            <div className="proposal-grid">
              <div className="summary-card preview-card">
                <div className="card-header">
                  <div>
                    <span className="section-label">Action Preview</span>
                    <strong>{previewModel.title}</strong>
                  </div>
                  <button className="secondary" type="button" onClick={() => onOpenPayload(activeProposal, "editable")}>
                    View Payload
                  </button>
                </div>
                <p className="muted">{previewModel.description}</p>
                <div className={`preview-lines preview-${previewModel.variant}`}>
                  {previewModel.lines.map((line) => (
                    <code key={line}>{line}</code>
                  ))}
                </div>
                {previewModel.footer ? <p className="muted">{previewModel.footer}</p> : null}
              </div>

              <div className="summary-card context-card">
                <span className="section-label">Decision Context</span>
                <MiniList title="Todo Delta" items={proposalContext.todoDelta} />
                <MiniTextBlock title="Rationale" text={proposalContext.rationale} />
                <MiniTextBlock title="Success Hypothesis" text={proposalContext.successHypothesis} />
                <MiniTextBlock
                  title="Latest Approval"
                  text={
                    activeProposalLatestApproval
                      ? `${activeProposalLatestApproval.decision} by ${activeProposalLatestApproval.approved_by}`
                      : "No prior approval on this node yet."
                  }
                />
                <MiniTextBlock
                  title="Latest Result"
                  text={activeProposalLatestResult?.execution_summary ?? "No execution result yet."}
                />
              </div>
            </div>

            <label>
              <span>Decision Comment</span>
              <input value={approvalComment} onChange={(event) => onApprovalCommentChange(event.target.value)} />
            </label>

            <div className="queue-strip">
              {currentTaskProposals.map((proposal) => (
                <span key={proposal.id} className={`queue-chip ${proposal.id === activeProposal.id ? "queue-chip-active" : ""}`}>
                  {proposal.node_label ?? `Proposal ${proposal.id}`}
                </span>
              ))}
            </div>

            <div className="button-row">
              <button type="button" onClick={onApproveProposal} disabled={busyAction === `approve-${activeProposal.id}`}>
                {busyAction === `approve-${activeProposal.id}` ? "Approving..." : "Approve"}
              </button>
              <button className="secondary" type="button" onClick={onRejectProposal} disabled={busyAction === `reject-${activeProposal.id}`}>
                {busyAction === `reject-${activeProposal.id}` ? "Rejecting..." : "Reject"}
              </button>
              <button className="secondary" type="button" onClick={onPauseProposalNode} disabled={busyAction === `pause-node-${activeProposal.id}`}>
                {busyAction === `pause-node-${activeProposal.id}` ? "Pausing..." : "Pause Node"}
              </button>
              <button className="secondary" type="button" onClick={() => onOpenPayload(activeProposal, "editable")}>
                View Payload
              </button>
            </div>
          </div>
        ) : null}

        {currentMode === "running" && currentTask ? (
          <div className="main-stage">
            <div className="action-intro">
              <h3>Task is running</h3>
              <p className="muted">No decision is needed right now. Use the right rail to watch progress or inspect the current node.</p>
            </div>

            <div className="summary-grid">
              <div className="summary-card">
                <span className="section-label">Current State</span>
                <p>{currentTask.status}</p>
              </div>
              <div className="summary-card">
                <span className="section-label">Next Expected Transition</span>
                <p>Either a node emits a new proposal or an executing node produces new evidence.</p>
              </div>
            </div>
          </div>
        ) : null}

        {currentMode === "awaiting-proposal" && currentTask ? (
          <div className="main-stage">
            <div className="action-intro">
              <h3>Preparing the next proposal</h3>
              <p className="muted">A node is currently in <code>awaiting_proposal</code>. Approval actions return here as soon as the worker produces a proposal.</p>
            </div>

            <div className="summary-grid">
              <div className="summary-card">
                <span className="section-label">What the system is doing</span>
                <p>The background worker is evaluating the node and preparing the next suggested action.</p>
              </div>
              <div className="summary-card">
                <span className="section-label">What you can do now</span>
                <p>Wait for the next proposal, or refresh to confirm whether it is ready yet.</p>
              </div>
            </div>

            <div className="button-row">
              <button type="button" onClick={onRefreshAwaitingProposal}>
                Refresh Status
              </button>
            </div>
          </div>
        ) : null}

        {currentMode === "terminal" && currentTask ? (
          <div className="main-stage">
            <div className="action-intro">
              <h3>Task finished</h3>
              <p className="muted">The main workflow is complete. Use the right rail and drawer to inspect the final evidence.</p>
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
                    {truncateText(taskNode.success_summary ?? taskNode.failure_summary ?? taskNode.status, 120)}
                  </p>
                ))}
              </div>
            </div>
          </div>
        ) : null}

        {!currentTask && currentMode !== "create" ? (
          <div className="empty-state">
            <h3>No task selected</h3>
            <p className="muted">Use the top bar to switch to a task or start a new one.</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function MiniList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="mini-block">
      <span className="section-label">{title}</span>
      {items.length > 0 ? (
        <ul className="mini-list">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">No items.</p>
      )}
    </div>
  );
}

function MiniTextBlock({ title, text }: { title: string; text: string }) {
  return (
    <div className="mini-block">
      <span className="section-label">{title}</span>
      <p className="clamp-4">{text}</p>
    </div>
  );
}
