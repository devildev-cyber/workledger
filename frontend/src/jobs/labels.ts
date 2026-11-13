import type { EntryKind, JobSummary, WorkOrderStatus } from "../api/types.ts";

export const FINISHED: WorkOrderStatus[] = ["completed", "closed", "cancelled"];

/** The button wording for each move a contractor can make. */
export function actionLabel(
  current: WorkOrderStatus,
  next: WorkOrderStatus,
): string {
  if (next === "in_progress")
    return current === "on_hold" ? "Resume work" : "Start work";
  if (next === "on_hold") return "Put on hold";
  if (next === "ready_for_review") return "Mark ready for review";
  return next;
}

// These need words, because the property team reads them to decide what happens next.
export const NOTE_PROMPTS: Partial<
  Record<WorkOrderStatus, { label: string; confirm: string }>
> = {
  on_hold: { label: "Why is the job on hold?", confirm: "Confirm on hold" },
  ready_for_review: {
    label: "What was done?",
    confirm: "Confirm ready for review",
  },
};

export const ENTRY_CHOICES: {
  value: Extract<EntryKind, "note" | "progress" | "clarification">;
  label: string;
}[] = [
  { value: "progress", label: "Progress update" },
  { value: "note", label: "Note" },
  { value: "clarification", label: "Question for the property team" },
];

export const TIMELINE_HEADLINES: Record<EntryKind, string> = {
  created: "Work order created",
  status_changed: "Status changed",
  edited: "Details changed",
  note: "Note",
  request_linked: "Request linked",
  assigned: "Assigned",
  unassigned: "Removed from the job",
  assignment_accepted: "Job accepted",
  assignment_declined: "Job declined",
  progress: "Progress update",
  clarification: "Question for the property team",
};

export type JobGroups = {
  waiting: JobSummary[];
  active: JobSummary[];
  finished: JobSummary[];
};

export function groupJobs(jobs: JobSummary[]): JobGroups {
  const groups: JobGroups = { waiting: [], active: [], finished: [] };
  for (const job of jobs) {
    if (FINISHED.includes(job.status)) groups.finished.push(job);
    else if (job.response === "pending") groups.waiting.push(job);
    else groups.active.push(job);
  }
  return groups;
}
