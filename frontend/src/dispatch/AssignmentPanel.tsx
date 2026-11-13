import { useState, type SubmitEventHandler } from "react";

import { api } from "../api/client.ts";
import type { Contractor, WorkOrder } from "../api/types.ts";
import { useAction } from "../api/useAction.ts";
import { useApiData } from "../api/useApiData.ts";
import { FormError } from "../components/FormError.tsx";
import { SelectField } from "../components/SelectField.tsx";
import { formatDate } from "../format.ts";
import { ASSIGNABLE_STATUSES, ENDED_LABELS } from "./labels.ts";
import { ResponseBadge } from "./ResponseBadge.tsx";

type AssignmentPanelProps = {
  organizationId: string;
  workOrder: WorkOrder;
  onChanged: () => void;
};

export function AssignmentPanel({
  organizationId,
  workOrder,
  onChanged,
}: AssignmentPanelProps) {
  const base = `/organizations/${organizationId}`;
  const url = `${base}/work-orders/${workOrder.id}`;
  const { data: contractors, error: loadError } = useApiData<Contractor[]>(
    `${base}/contractors`,
  );
  const [choice, setChoice] = useState("");
  const { busy, error, run, fail } = useAction();

  const current = workOrder.assignment;
  const canChange = ASSIGNABLE_STATUSES.includes(workOrder.status);
  const others = (contractors ?? []).filter(
    (item) => item.id !== current?.contractor_id,
  );

  const handleAssign: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault();
    if (choice === "") {
      fail("Choose a contractor.");
      return;
    }
    const saved = await run(() =>
      api(`${url}/assign`, { method: "POST", body: { contractor_id: choice } }),
    );
    if (saved) {
      setChoice("");
      onChanged();
    }
  };

  const handleRemove = async () => {
    const saved = await run(() => api(`${url}/unassign`, { method: "POST" }));
    if (saved) onChanged();
  };

  return (
    <div className="space-y-4">
      {current ? (
        <div className="flex flex-wrap items-center gap-3">
          <p>
            <span className="font-medium">{current.contractor_name}</span>
            <span className="text-sm text-slate-600">
              {" "}
              assigned by {current.assigned_by_name} on{" "}
              {formatDate(current.assigned_at)}
            </span>
          </p>
          <ResponseBadge response={current.response} />
        </div>
      ) : (
        <p className="text-slate-600">No contractor is assigned.</p>
      )}

      {canChange ? (
        <form
          onSubmit={handleAssign}
          aria-label={current ? "Reassign" : "Assign a contractor"}
          className="space-y-3 rounded border border-slate-200 bg-white p-4"
        >
          <FormError message={error ?? loadError} />
          {contractors && contractors.length === 0 ? (
            <p className="text-sm text-slate-600">
              No one holds the contractor role yet. Invite a contractor from the
              People page.
            </p>
          ) : (
            <SelectField
              id="work-order-contractor"
              label={current ? "Reassign to" : "Contractor"}
              placeholder="Choose a contractor"
              value={choice}
              options={others.map((item) => ({
                value: item.id,
                label: `${item.full_name} (${item.active_jobs} open ${item.active_jobs === 1 ? "job" : "jobs"})`,
              }))}
              onChange={setChoice}
            />
          )}
          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              disabled={busy}
              className="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60"
            >
              {current ? "Reassign" : "Assign"}
            </button>
            {current && (
              <button
                type="button"
                disabled={busy}
                onClick={handleRemove}
                className="rounded border border-slate-300 px-4 py-2 disabled:opacity-60"
              >
                Remove contractor
              </button>
            )}
          </div>
        </form>
      ) : (
        <p className="text-sm text-slate-600">
          This work order can no longer be assigned or reassigned.
        </p>
      )}

      {workOrder.assignment_history.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-slate-700">
            Assignment history
          </h3>
          <ol aria-label="Assignment history" className="space-y-2 text-sm">
            {workOrder.assignment_history.map((item) => (
              <li
                key={item.id}
                className="rounded border border-slate-200 bg-white p-3"
              >
                <p>
                  <span className="font-medium">{item.contractor_name}</span>{" "}
                  <span className="text-slate-600">
                    from {formatDate(item.assigned_at)} by{" "}
                    {item.assigned_by_name}
                  </span>
                </p>
                <p className="text-slate-700">
                  {item.ended_at
                    ? `${item.ended_reason ? ENDED_LABELS[item.ended_reason] : "Ended"} on ${formatDate(item.ended_at)}`
                    : "Current"}
                  {item.response !== "pending" &&
                    ` · ${item.response === "accepted" ? "Accepted" : "Declined"}`}
                </p>
                {item.decline_reason && (
                  <p className="whitespace-pre-wrap text-slate-800">
                    Reason: {item.decline_reason}
                  </p>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
