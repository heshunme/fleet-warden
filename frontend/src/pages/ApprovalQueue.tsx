import { useState } from "react";

import { approveProposal, pauseProposalNode, rejectProposal } from "../lib/api";
import type { ProposalRecord } from "../types";
import { SectionCard } from "../components/SectionCard";

interface ApprovalQueueProps {
  proposals: ProposalRecord[];
  onProposalHandled: () => void;
}

export function ApprovalQueue({ proposals, onProposalHandled }: ApprovalQueueProps) {
  const [comment, setComment] = useState("Approved from UI");

  const handleApprove = async (proposal: ProposalRecord) => {
    await approveProposal(proposal.id, { comment });
    onProposalHandled();
  };

  const handleReject = async (proposalId: number) => {
    await rejectProposal(proposalId, "Rejected from approval queue");
    onProposalHandled();
  };

  const handlePause = async (proposalId: number) => {
    await pauseProposalNode(proposalId, "Paused from approval queue");
    onProposalHandled();
  };

  return (
    <SectionCard title="Approval Queue">
      <label>
        <span>Approval Comment</span>
        <input value={comment} onChange={(event) => setComment(event.target.value)} />
      </label>
      <div className="approval-list">
        {proposals.map((proposal) => (
          <article key={proposal.id} className="approval-card">
            <div className="panel-header">
              <h3>{proposal.summary}</h3>
              <span className={`risk risk-${proposal.risk_level}`}>{proposal.risk_level}</span>
            </div>
            <pre>{JSON.stringify(proposal.editable_content, null, 2)}</pre>
            <div className="button-row">
              <button type="button" onClick={() => handleApprove(proposal)}>Approve</button>
              <button className="secondary" type="button" onClick={() => handlePause(proposal.id)}>Pause Node</button>
              <button className="danger" type="button" onClick={() => handleReject(proposal.id)}>Reject</button>
            </div>
          </article>
        ))}
        {proposals.length === 0 ? <p className="muted">No pending proposals right now.</p> : null}
      </div>
    </SectionCard>
  );
}
