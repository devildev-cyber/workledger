import { MemberChoiceSection } from './MemberChoiceSection.tsx'

export function OwnersSection({ url }: { url: string }) {
  return (
    <MemberChoiceSection
      url={url}
      name="owners"
      wording={{
        heading: 'Property owners',
        intro:
          'Property owners decide on estimates above this property’s approval threshold, and see nothing else here.',
        loading: 'Loading property owners…',
        empty:
          'No one has the property owner role yet. Invite a property owner from the People page.',
        legend: 'Owners of this property',
        save: 'Save owners',
        saved: 'Owners saved.',
      }}
    />
  )
}
