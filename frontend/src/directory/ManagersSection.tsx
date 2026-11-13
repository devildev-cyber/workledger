import { MemberChoiceSection } from './MemberChoiceSection.tsx'

export function ManagersSection({ url }: { url: string }) {
  return (
    <MemberChoiceSection
      url={url}
      name="managers"
      wording={{
        heading: 'Managers',
        intro: 'Managers see and act on only the properties assigned to them.',
        loading: 'Loading managers…',
        empty: 'No one has the manager role yet. Invite a manager from the People page.',
        legend: 'Managers of this property',
        save: 'Save managers',
        saved: 'Managers saved.',
      }}
    />
  )
}
