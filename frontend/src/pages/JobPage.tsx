import { Link, useNavigate, useParams } from "react-router";

import type { Job } from "../api/types.ts";
import { useApiData } from "../api/useApiData.ts";
import { useCurrentUser } from "../auth/auth-context.ts";
import { FileList } from "../dispatch/FileList.tsx";
import { ResponseBadge } from "../dispatch/ResponseBadge.tsx";
import { addressLine, formatDay } from "../format.ts";
import { EntryForm } from "../jobs/EntryForm.tsx";
import { FINISHED } from "../jobs/labels.ts";
import { ReplyPanel } from "../jobs/ReplyPanel.tsx";
import { StatusActions } from "../jobs/StatusActions.tsx";
import { Timeline } from "../jobs/Timeline.tsx";
import {
  findMembership,
  isContractor,
  myJobsPath,
} from "../organizations/organizations.ts";
import { CATEGORY_LABELS, URGENCY_SHORT } from "../requests/labels.ts";
import { UploadForm } from "../requests/UploadForm.tsx";
import { WorkOrderStatusBadge } from "../workorders/WorkOrderStatusBadge.tsx";
import { NotFoundPage } from "./NotFoundPage.tsx";

export function JobPage() {
  const user = useCurrentUser();
  const { organizationId, workOrderId } = useParams();
  const membership = findMembership(user, organizationId);

  if (!membership || !workOrderId || !isContractor(membership.roles)) {
    return <NotFoundPage />;
  }

  return (
    <JobDetail
      organizationId={membership.organization_id}
      workOrderId={workOrderId}
    />
  );
}

function JobDetail({
  organizationId,
  workOrderId,
}: {
  organizationId: string;
  workOrderId: string;
}) {
  const navigate = useNavigate();
  const apiUrl = `/organizations/${organizationId}/my-jobs/${workOrderId}`;
  const { data: job, error, loading, reload } = useApiData<Job>(apiUrl);

  if (loading) {
    return (
      <p role="status" className="text-slate-600">
        Loading job…
      </p>
    );
  }
  // The same answer for a job that is someone else's and one that does not exist.
  if (error || !job) {
    return <NotFoundPage />;
  }

  const accepted = job.response === "accepted";
  const finished = FINISHED.includes(job.status);

  return (
    <div className="space-y-8">
      <div className="space-y-1">
        <Link
          to={myJobsPath(organizationId)}
          className="inline-block py-2 text-sm text-slate-600 underline"
        >
          My jobs
        </Link>
        <h1 className="text-2xl font-semibold">{job.title}</h1>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-slate-600">{job.reference}</span>
          <WorkOrderStatusBadge status={job.status} />
          <ResponseBadge response={job.response} />
          {job.overdue && (
            <span className="rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-900">
              Overdue
            </span>
          )}
        </div>
      </div>

      {job.can_accept && (
        <ReplyPanel
          url={apiUrl}
          onReplied={(reply) => {
            if (reply === "declined") void navigate(myJobsPath(organizationId));
            else reload();
          }}
        />
      )}

      <section aria-labelledby="job-details-heading" className="space-y-3">
        <h2 id="job-details-heading" className="text-xl font-semibold">
          The job
        </h2>
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
          <dt className="text-slate-600">Where</dt>
          <dd>
            {job.unit_label
              ? `${job.building_name ? `${job.building_name} · ` : ""}${job.unit_label}, `
              : ""}
            {job.property_name}
            <span className="block text-slate-700">{addressLine(job)}</span>
          </dd>
          <dt className="text-slate-600">Kind of work</dt>
          <dd>{CATEGORY_LABELS[job.category]}</dd>
          <dt className="text-slate-600">Priority</dt>
          <dd>{URGENCY_SHORT[job.priority]}</dd>
          <dt className="text-slate-600">Due date</dt>
          <dd>{job.due_date ? formatDay(job.due_date) : "Not set"}</dd>
          {accepted && job.residents.length > 0 && (
            <>
              <dt className="text-slate-600">Resident</dt>
              <dd>{job.residents.join(", ")}</dd>
            </>
          )}
          {accepted && job.access_notes.length > 0 && (
            <>
              <dt className="text-slate-600">Getting in</dt>
              <dd className="space-y-1">
                {job.access_notes.map((note) => (
                  <span key={note} className="block whitespace-pre-wrap">
                    {note}
                  </span>
                ))}
              </dd>
            </>
          )}
        </dl>
        <p className="whitespace-pre-wrap">{job.scope}</p>
        {!accepted && (
          <p className="text-sm text-slate-600">
            The resident’s name and entry instructions appear once you accept
            the job.
          </p>
        )}
        <p className="text-sm text-slate-600">
          Questions for the resident go through the property team. Use “Question
          for the property team” below.
        </p>
      </section>

      <StatusActions
        url={`${apiUrl}/status`}
        current={job.status}
        allowed={job.allowed_statuses}
        onChanged={reload}
      />

      <section aria-labelledby="evidence-heading" className="space-y-3">
        <h2 id="evidence-heading" className="text-xl font-semibold">
          Photos and documents
        </h2>
        <FileList
          files={job.attachments}
          baseUrl={`${apiUrl}/attachments`}
          note={(file) =>
            job.attachments.find((item) => item.id === file.id)?.mine
              ? "Yours"
              : null
          }
        />
        {accepted && !finished && (
          <UploadForm
            url={`${apiUrl}/attachments`}
            label="Add a photo of the work"
            onUploaded={reload}
          />
        )}
      </section>

      <section aria-labelledby="updates-heading" className="space-y-3">
        <h2 id="updates-heading" className="text-xl font-semibold">
          Updates
        </h2>
        <Timeline entries={job.timeline} />
        {accepted && !finished && (
          <EntryForm url={`${apiUrl}/entries`} onSaved={reload} />
        )}
      </section>
    </div>
  );
}
