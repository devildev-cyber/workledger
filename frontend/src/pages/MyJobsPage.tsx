import { Link, useParams } from "react-router";

import type { JobSummary } from "../api/types.ts";
import { useApiData } from "../api/useApiData.ts";
import { useCurrentUser } from "../auth/auth-context.ts";
import { FormError } from "../components/FormError.tsx";
import { ResponseBadge } from "../dispatch/ResponseBadge.tsx";
import { formatDay } from "../format.ts";
import {
  findMembership,
  isContractor,
  myJobsPath,
} from "../organizations/organizations.ts";
import { URGENCY_SHORT } from "../requests/labels.ts";
import { groupJobs } from "../jobs/labels.ts";
import { WorkOrderStatusBadge } from "../workorders/WorkOrderStatusBadge.tsx";
import { NotFoundPage } from "./NotFoundPage.tsx";

export function MyJobsPage() {
  const user = useCurrentUser();
  const { organizationId } = useParams();
  const membership = findMembership(user, organizationId);

  if (!membership || !isContractor(membership.roles)) {
    return <NotFoundPage />;
  }

  return <JobList organizationId={membership.organization_id} />;
}

function JobList({ organizationId }: { organizationId: string }) {
  const {
    data: jobs,
    error,
    loading,
  } = useApiData<JobSummary[]>(myJobsPath(organizationId));

  if (loading) {
    return (
      <p role="status" className="text-slate-600">
        Loading your jobs…
      </p>
    );
  }

  const groups = groupJobs(jobs ?? []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">My jobs</h1>
      <FormError message={error} />
      {jobs && jobs.length === 0 && (
        <p className="text-slate-600">
          You have no jobs right now. New jobs appear here when the property
          team assigns them.
        </p>
      )}
      <JobGroup
        title="Waiting for your reply"
        jobs={groups.waiting}
        organizationId={organizationId}
      />
      <JobGroup
        title="In hand"
        jobs={groups.active}
        organizationId={organizationId}
      />
      <JobGroup
        title="Finished"
        jobs={groups.finished}
        organizationId={organizationId}
      />
    </div>
  );
}

function JobGroup({
  title,
  jobs,
  organizationId,
}: {
  title: string;
  jobs: JobSummary[];
  organizationId: string;
}) {
  if (jobs.length === 0) return null;

  return (
    <section aria-label={title} className="space-y-3">
      <h2 className="text-lg font-semibold">{title}</h2>
      <ul className="space-y-3">
        {jobs.map((job) => (
          <li key={job.id}>
            <Link
              to={`${myJobsPath(organizationId)}/${job.id}`}
              className="block space-y-2 rounded border border-slate-200 bg-white p-4"
            >
              <span className="block text-base font-medium underline">
                {job.title}
              </span>
              <span className="block text-sm text-slate-700">
                {job.unit_label ? `${job.unit_label}, ` : ""}
                {job.property_name}
              </span>
              <span className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-slate-600">{job.reference}</span>
                <WorkOrderStatusBadge status={job.status} />
                {job.response === "pending" && (
                  <ResponseBadge response={job.response} />
                )}
                <span className="text-slate-600">
                  {URGENCY_SHORT[job.priority]}
                </span>
                {job.due_date && (
                  <span className="text-slate-600">
                    Due {formatDay(job.due_date)}
                  </span>
                )}
                {job.overdue && (
                  <span className="rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-900">
                    Overdue
                  </span>
                )}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
