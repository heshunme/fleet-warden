import { useState } from "react";

import { approveProposal, pauseProposalNode, rejectProposal } from "../lib/api";
import { canHandleProposal } from "../lib/guards";
import type { ProposalRecord } from "../types";
import { SectionCard } from "../components/SectionCard";

interface ApprovalQueueProps {
  proposals: ProposalRecord[];
  onProposalHandled: () => void;
}

export function ApprovalQueue({ proposals, onProposalHandled }: ApprovalQueueProps) {
  const [comment, setComment] = useState("Approved from UI");
  const [busyProposalIds, setBusyProposalIds] = useState<number[]>([]);

  const setProposalBusy = (proposalId: number, busy: boolean) => {
    setBusyProposalIds((current) => (
      busy
        ? (current.includes(proposalId) ? current : [...current, proposalId])
        : current.filter((id) => id !== proposalId)
    ));
  };

  const handleApprove = async (proposal: ProposalRecord) => {
    setProposalBusy(proposal.id, true);
    try {
      await approveProposal(proposal.id, { comment });
      onProposalHandled();
    } finally {
      setProposalBusy(proposal.id, false);
    }
  };

  const handleReject = async (proposalId: number) => {
    setProposalBusy(proposalId, true);
    try {
      await rejectProposal(proposalId, "Rejected from approval queue");
      onProposalHandled();
    } finally {
      setProposalBusy(proposalId, false);
    }
  };

  const handlePause = async (proposalId: number) => {
    setProposalBusy(proposalId, true);
    try {
      await pauseProposalNode(proposalId, "Paused from approval queue");
      onProposalHandled();
    } finally {
      setProposalBusy(proposalId, false);
    }
  };

  return (
    <SectionCard title="Approval Queue">
      <label>
        <span>Approval Comment</span>
        <input value={comment} onChange={(event) => setComment(event.target.value)} />
      </label>
      <div className="approval-list">
        {proposals.map((proposal) => {
          const disabled = !canHandleProposal(proposal) || busyProposalIds.includes(proposal.id);
          return (
            <article key={proposal.id} className="approval-card">
              <div className="panel-header">
                <h3>{proposal.summary}</h3>
                <span className={`risk risk-${proposal.risk_level}`}>{proposal.risk_level}</span>
              </div>
              <pre>{JSON.stringify(proposal.editable_content, null, 2)}</pre>
              {!canHandleProposal(proposal) ? (
                <p className="muted">This proposal is no longer pending and cannot be handled from the queue.</p>
              ) : null}
              <div className="button-row">
                <button type="button" onClick={() => handleApprove(proposal)} disabled={disabled}>Approve</button>
                <button className="secondary" type="button" onClick={() => handlePause(proposal.id)} disabled={disabled}>Pause Node</button>
                <button className="danger" type="button" onClick={() => handleReject(proposal.id)} disabled={disabled}>Reject</button>
              </div>
            </article>
          );
        })}
        {proposals.length === 0 ? <p className="muted">No pending proposals right now.</p> : null}
      </div>
    </SectionCard>
  );
}
