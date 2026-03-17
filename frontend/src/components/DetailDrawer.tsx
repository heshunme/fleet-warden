import type { ReactNode } from "react";

import { formatTimestamp } from "../lib/presenters";
import type { DetailDrawerState } from "../types";

interface DetailDrawerProps {
  drawer: DetailDrawerState | null;
  onClose: () => void;
  onPayloadViewChange: (view: "editable" | "raw") => void;
}

export function DetailDrawer({ drawer, onClose, onPayloadViewChange }: DetailDrawerProps) {
  if (!drawer) {
    return null;
  }

  return (
    <>
      <button type="button" className="drawer-backdrop" onClick={onClose} aria-label="Close drawer" />
      <aside className="detail-drawer">
        <div className="drawer-header">
          <div>
            <p className="eyebrow">Detail Drawer</p>
            <h2>{getDrawerTitle(drawer)}</h2>
          </div>
          <button className="secondary" type="button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="drawer-body">
          {drawer.kind === "taskspec" ? (
            <>
              <DrawerSection title="Goal">
                <p>{drawer.taskSpec.goal}</p>
              </DrawerSection>
              <DrawerSection title="Constraints">
                <StringList items={drawer.taskSpec.constraints} />
              </DrawerSection>
              <DrawerSection title="Success Criteria">
                <StringList items={drawer.taskSpec.success_criteria} />
              </DrawerSection>
              <DrawerSection title="Risk Notes">
                <StringList items={drawer.taskSpec.risk_notes} />
              </DrawerSection>
              <DrawerSection title="Initial Todo">
                <StringList items={drawer.taskSpec.initial_todo_template} />
              </DrawerSection>
              {drawer.taskSpec.operator_notes ? (
                <DrawerSection title="Operator Notes">
                  <p>{drawer.taskSpec.operator_notes}</p>
                </DrawerSection>
              ) : null}
            </>
          ) : null}

          {drawer.kind === "payload" ? (
            <>
              <div className="tab-strip">
                <button
                  type="button"
                  className={`tab-chip ${drawer.view === "editable" ? "tab-chip-active" : ""}`}
                  onClick={() => onPayloadViewChange("editable")}
                >
                  Editable
                </button>
                {Object.keys(drawer.proposal.content).length > 0 ? (
                  <button
                    type="button"
                    className={`tab-chip ${drawer.view === "raw" ? "tab-chip-active" : ""}`}
                    onClick={() => onPayloadViewChange("raw")}
                  >
                    Raw
                  </button>
                ) : null}
              </div>
              <DrawerSection title={drawer.view === "editable" ? "Editable Payload" : "Raw Payload"}>
                <pre>{JSON.stringify(drawer.view === "editable" ? drawer.proposal.editable_content : drawer.proposal.content, null, 2)}</pre>
              </DrawerSection>
            </>
          ) : null}

          {drawer.kind === "execution" ? (
            <>
              <DrawerSection title="Summary">
                <p>{drawer.executionResult.execution_summary}</p>
                <p className="muted">
                  {drawer.nodeLabel ?? "Unknown node"} · {drawer.proposalSummary ?? "No proposal summary"} · ended {formatTimestamp(drawer.executionResult.ended_at)}
                </p>
              </DrawerSection>
              {drawer.executionResult.stdout ? (
                <DrawerSection title="Stdout">
                  <pre>{drawer.executionResult.stdout}</pre>
                </DrawerSection>
              ) : null}
              {drawer.executionResult.stderr ? (
                <DrawerSection title="Stderr">
                  <pre>{drawer.executionResult.stderr}</pre>
                </DrawerSection>
              ) : null}
              <DrawerSection title="Structured Output">
                <pre>{JSON.stringify(drawer.executionResult.structured_output, null, 2)}</pre>
              </DrawerSection>
            </>
          ) : null}

          {drawer.kind === "event" ? (
            <>
              <DrawerSection title="Event">
                <p>{drawer.event.event_type}</p>
                <p className="muted">{formatTimestamp(drawer.event.created_at)}</p>
              </DrawerSection>
              <DrawerSection title="Payload">
                <pre>{JSON.stringify(drawer.event.payload, null, 2)}</pre>
              </DrawerSection>
            </>
          ) : null}
        </div>
      </aside>
    </>
  );
}

function getDrawerTitle(drawer: DetailDrawerState): string {
  if (drawer.kind === "taskspec") {
    return "TaskSpec Detail";
  }
  if (drawer.kind === "payload") {
    return "Proposal Payload";
  }
  if (drawer.kind === "execution") {
    return "Execution Output";
  }
  return "Event Payload";
}

function DrawerSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="summary-card drawer-section">
      <span className="section-label">{title}</span>
      {children}
    </section>
  );
}

function StringList({ items }: { items: string[] }) {
  return items.length > 0 ? (
    <ul className="mini-list">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  ) : (
    <p className="muted">No items.</p>
  );
}
