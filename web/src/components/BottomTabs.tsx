export type Tab = 'mapa' | 'festas' | 'locais'

export function BottomTabs({ tab, onTab }: { tab: Tab; onTab: (t: Tab) => void }) {
  const tabs: { key: Tab; label: string }[] = [
    { key: 'mapa', label: 'MAPA' }, { key: 'festas', label: 'FESTAS' }, { key: 'locais', label: 'LOCAIS' },
  ]
  return (
    <div className="tabbar">
      {tabs.map((t) => (
        <button key={t.key} className={t.key === tab ? 'on' : ''} onClick={() => onTab(t.key)}>
          {t.label}
        </button>
      ))}
    </div>
  )
}
