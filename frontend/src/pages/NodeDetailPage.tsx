import type { TaskNodeRecord } from "../types";
import { SectionCard } from "../components/SectionCard";

interface NodeDetailPageProps {
  taskNode: TaskNodeRecord | null;
}

export function NodeDetailPage({ taskNode }: NodeDetailPageProps) {
  if (!taskNode) {
    return (
      <SectionCard title="Node Detail">
        <p className="muted">Select a node from the task overview to inspect its rounds and outputs.</p>
      </SectionCard>
    );
  }

  const latestRound = taskNode.rounds.at(-1);
  const latestProposal = latestRound?.proposals.at(-1);
  const latestResult = latestProposal?.execution_results.at(-1);

  return (
    <SectionCard title={`Node Detail · ${taskNode.node.host_alias}`}>
      <div className="grid-two">
        <div className="stack">
          <div className="stat-grid">
            <div className="stat"><span>Status</span><strong>{taskNode.status}</strong></div>
            <div className="stat"><span>Round</span><strong>{taskNode.current_round}</strong></div>
            <div className="stat"><span>User Input</span><strong>{taskNode.needs_user_input ? "Yes" : "No"}</strong></div>
            <div className="stat"><span>Last Result</span><strong>{taskNode.last_result_at ?? "N/A"}</strong></div>
          </div>
          <h3>Todo</h3>
          <ul>
            {(taskNode.agent_state?.todo_items ?? []).map((item) => <li key={item}>{item}</li>)}
          </ul>
          <h3>Current Proposal</h3>
          <pre>{JSON.stringify(latestProposal?.editable_content ?? {}, null, 2)}</pre>
        </div>
        <div className="stack">
          <h3>Approvals</h3>
          <ul>
            {(latestProposal?.approvals ?? []).map((approval) => (
              <li key={approval.id}>
                {approval.decision} by {approval.approved_by}
              </li>
            ))}
          </ul>
          <h3>Execution Result</h3>
          <details open={Boolean(latestResult)}>
            <summary>{latestResult?.execution_summary ?? "No execution yet"}</summary>
            <pre>{latestResult?.stdout ?? ""}</pre>
            {latestResult?.stderr ? <pre>{latestResult.stderr}</pre> : null}
          </details>
          <h3>History</h3>
          <div className="event-stream">
            {taskNode.rounds.map((round) => (
              <article key={round.id} className="event-row">
                <strong>Round {round.index}</strong>
                <span>{round.status}</span>
                <small>{round.proposals.map((proposal) => proposal.summary).join(" | ")}</small>
              </article>
            ))}
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

