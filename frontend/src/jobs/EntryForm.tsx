import { useState, type SubmitEventHandler } from "react";

import { api } from "../api/client.ts";
import type { EntryKind } from "../api/types.ts";
import { useAction } from "../api/useAction.ts";
import { FormError } from "../components/FormError.tsx";
import { SelectField } from "../components/SelectField.tsx";
import { TextAreaField } from "../components/TextAreaField.tsx";
import { ENTRY_CHOICES } from "./labels.ts";

export function EntryForm({
  url,
  onSaved,
}: {
  url: string;
  onSaved: () => void;
}) {
  const [kind, setKind] = useState<EntryKind>("progress");
  const [body, setBody] = useState("");
  const { busy, error, run, fail } = useAction();

  const handleSubmit: SubmitEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault();
    if (body.trim() === "") {
      fail("Write something first.");
      return;
    }
    const saved = await run(() =>
      api(url, { method: "POST", body: { body, kind } }),
    );
    if (saved) {
      setBody("");
      onSaved();
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="Add an update"
      className="space-y-3 rounded border border-slate-200 bg-white p-4"
    >
      <FormError message={error} />
      <SelectField
        id="job-entry-kind"
        label="Kind of update"
        value={kind}
        options={ENTRY_CHOICES}
        onChange={(value) => setKind(value as EntryKind)}
      />
      <TextAreaField
        id="job-entry-body"
        label="Message"
        maxLength={2000}
        rows={3}
        value={body}
        onChange={setBody}
      />
      <button
        type="submit"
        disabled={busy}
        className="min-h-12 w-full rounded bg-slate-900 px-4 py-3 font-medium text-white disabled:opacity-60 sm:w-auto"
      >
        Send update
      </button>
    </form>
  );
}
