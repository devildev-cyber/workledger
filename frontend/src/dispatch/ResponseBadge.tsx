import type { AssignmentResponse } from "../api/types.ts";
import { RESPONSE_LABELS } from "./labels.ts";

const STYLES: Record<AssignmentResponse, string> = {
  pending: "bg-amber-100 text-amber-900",
  accepted: "bg-green-100 text-green-900",
  declined: "bg-slate-200 text-slate-800",
};

export function ResponseBadge({ response }: { response: AssignmentResponse }) {
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-medium ${STYLES[response]}`}
    >
      {RESPONSE_LABELS[response]}
    </span>
  );
}
