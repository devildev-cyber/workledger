import type { ReactNode } from 'react'
import { useParams } from 'react-router'

import type { Role } from '../api/types.ts'
import { useCurrentUser } from '../auth/auth-context.ts'
import {
  canInvite,
  canSeeDirectory,
  findMembership,
  isContractor,
  isPropertyOwner,
  isResident,
} from '../organizations/organizations.ts'

type Topic = { title: string; steps: ReactNode[] }

const RESIDENT: Topic[] = [
  {
    title: 'Report a problem',
    steps: [
      'Open My requests and choose the button to report a problem.',
      'Say what is wrong and where. Pick the urgency honestly: urgent is for danger or damage that is spreading, such as a gas smell, flooding or no heat in winter.',
      'Add photos if you can. Photos (JPEG, PNG, WebP) and PDF documents are accepted.',
    ],
  },
  {
    title: 'Follow what happens next',
    steps: [
      'Each request has a timeline. You are told when it is reviewed, when work is planned and when it is done.',
      'You can add a message or cancel a request until work has started.',
      'Contractor prices and internal notes are never shown to you.',
    ],
  },
]

const CONTRACTOR: Topic[] = [
  {
    title: 'Your jobs',
    steps: [
      'My jobs lists the work assigned to you. Open a job to see the place, the access notes and the due date.',
      'Accept or decline a new job. If you decline, say why so it can be reassigned.',
      'If the job needs a price, send an estimate. Work on a job that needs approval cannot start until the owner approves it.',
    ],
  },
  {
    title: 'Finishing a job',
    steps: [
      'Record what you did and the final cost when you mark the job done, and add photos of the result.',
      'The manager reviews the work. If it is sent back, the reason is on the job.',
    ],
  },
]

const OWNER: Topic[] = [
  {
    title: 'Approvals',
    steps: [
      'Approvals lists repair estimates above the approval limit of your properties.',
      'Approve or reject each one. A reason is required when you reject, and it is kept with the decision.',
      'Open the summary on that page to see what was approved and spent in a period, and to download it as a spreadsheet.',
    ],
  },
]

const MANAGER: Topic[] = [
  {
    title: 'Handle requests',
    steps: [
      'Requests shows everything residents reported for your properties. Review a request, then turn it into a work order or decline it with a reason.',
      'Several requests about the same problem can be linked to one work order.',
    ],
  },
  {
    title: 'Dispatch and review work',
    steps: [
      'On a work order, assign a contractor, set the priority and due date, and record the estimate.',
      'An estimate above the property limit goes to the owner for approval before work starts.',
      'When the contractor finishes, check the work, then verify it or send it back with a reason.',
    ],
  },
  {
    title: 'Reports',
    steps: [
      'Reports shows open work, overdue and blocked jobs, time to resolve, contractor workload, repeat problems and repair spend. Dates are in UTC, and both the first and last day are included.',
      'Download work orders, requests or estimates as a spreadsheet. Names and contact details of residents are never included, and every download is recorded.',
    ],
  },
]

const PEOPLE: Topic[] = [
  {
    title: 'People',
    steps: [
      'People is where you invite residents, contractors and owners, and other managers if you are an administrator. An invitation is an email link that works once and expires. You can revoke one that is still waiting.',
      'Remove access there when someone leaves. Their history stays in the records.',
    ],
  },
]

const EVERYONE: Topic[] = [
  {
    title: 'Your account',
    steps: [
      'Forgot your password? Use the link on the sign-in page. A reset link is emailed to you and works once.',
      'After 5 wrong passwords the account is locked for 15 minutes. This protects you from guessing. Waiting, or resetting your password by email, is the way back in.',
      'You are signed out after a long time away. Sign in again and nothing is lost.',
    ],
  },
  {
    title: 'Notifications',
    steps: [
      'The Notifications link shows what needs your attention. The same news is sent to you by email.',
    ],
  },
]

export function HelpPage() {
  const user = useCurrentUser()
  const { organizationId } = useParams()
  const membership = findMembership(user, organizationId)
  const roles: Role[] = membership?.roles ?? []

  const groups: { title: string; topics: Topic[] }[] = []

  if (isResident(roles)) groups.push({ title: 'For residents', topics: RESIDENT })
  if (isContractor(roles)) groups.push({ title: 'For contractors', topics: CONTRACTOR })
  if (isPropertyOwner(roles)) groups.push({ title: 'For property owners', topics: OWNER })
  if (canSeeDirectory(roles)) groups.push({ title: 'For managers', topics: MANAGER })
  if (canInvite(roles)) groups.push({ title: 'Inviting people', topics: PEOPLE })

  groups.push({ title: 'For everyone', topics: EVERYONE })

  return (
    <article className="space-y-8">
      <h1 className="text-2xl font-semibold">Help</h1>
      {groups.map((group) => (
        <section key={group.title} aria-labelledby={headingId(group.title)} className="space-y-4">
          <h2 id={headingId(group.title)} className="text-xl font-semibold">
            {group.title}
          </h2>
          {group.topics.map((topic) => (
            <div key={topic.title} className="space-y-2">
              <h3 className="font-semibold">{topic.title}</h3>
              <ul className="list-disc space-y-1 pl-6 text-slate-700">
                {topic.steps.map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      ))}
    </article>
  )
}

function headingId(title: string): string {
  return `Help-${title.replace(/\s+/g, '')}`
}
