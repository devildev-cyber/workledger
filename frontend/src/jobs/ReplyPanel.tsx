import { useState, type SubmitEventHandler } from "react";

import { api } from "../api/client.ts";
import { useAction } from "../api/useAction.ts";
import { FormError } from "../components/FormError.tsx";
import { TextAreaField } from "../components/TextAreaField.tsx";

type ReplyPanelProps = {
  url: string;
  // Called after a reply. Declining removes the job from this contractor, so it says which.
  onReplied: (reply: "accepted" | "declined") => void;
};

export function ReplyPanel({ url, onReplied }: ReplyPanelProps) {
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const { busy, error, run, fail } = useAction();

  const accept = async () => {
    const saved = await run(() => api(`${url}/accept`, { method: "POST" }));
    if (saved) onReplied("accepted");
  };

  const decline: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault();
    if (reason.trim().length < 3) {
      fail("Say why you cannot take this job.");
      return;
    }
    const saved = await run(() =>
      api(`${url}/decline`, { method: "POST", body: { reason } }),
    );
    if (saved) onReplied("declined");
  };

  return (
    <section
      aria-labelledby="reply-heading"
      className="space-y-3 rounded border border-amber-300 bg-amber-50 p-4"
    >
      <h2 id="reply-heading" className="text-lg font-semibold">
        Can you take this job?
      </h2>
      {declining ? (
        <form
          onSubmit={decline}
          aria-label="Decline the job"
          className="space-y-3"
        >
          <FormError message={error} />
          <TextAreaField
            id="decline-reason"
            label="Why can you not take it?"
            maxLength={1000}
            rows={3}
            value={reason}
            onChange={setReason}
          />
          <div className="flex flex-col gap-3 sm:flex-row">
            <button
              type="submit"
              disabled={busy}
              className="min-h-12 rounded bg-slate-900 px-4 py-3 font-medium text-white disabled:opacity-60"
            >
              Decline job
            </button>
            <button
              type="button"
              onClick={() => setDeclining(false)}
              className="min-h-12 rounded border border-slate-300 bg-white px-4 py-3"
            >
              Back
            </button>
          </div>
        </form>
      ) : (
        <div className="space-y-3">
          <FormError message={error} />
          <div className="flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              disabled={busy}
              onClick={accept}
              className="min-h-12 rounded bg-slate-900 px-4 py-3 font-medium text-white disabled:opacity-60"
            >
              Accept job
            </button>
            <button
              type="button"
              onClick={() => setDeclining(true)}
              className="min-h-12 rounded border border-slate-300 bg-white px-4 py-3"
            >
              Decline
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
