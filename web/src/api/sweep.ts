import { getJson, postJson } from './client'

export interface SweepFesta { event_id: number; name: string; starts_at: string | null; anchored: boolean }
export interface SweepAcoes {
  add?: number; cancel?: number; update?: number; cancel_candidate?: number; update_candidate?: number
  ignore?: Record<string, number>
}
export interface SweepItem {
  venue_id: number | null; venue_name: string | null; handle: string
  status: 'ok' | 'falha'; posts_novos: number; flyers: string[]; festas: SweepFesta[]; erro?: string
  acoes?: SweepAcoes
}
export interface SweepOut {
  id: number; label: string | null; status: 'running' | 'done' | 'error'
  phase: 'iniciando' | 'varrendo' | 'extraindo' | 'done'
  total_handles: number; done_handles: number
  report: SweepItem[]; diff: { novas_festas: number; venues_com_pin_novo: string[] } | null
  error: string | null; started_at: string; finished_at: string | null
}

export function startSweep(lat: number, lng: number, km: number): Promise<{ id: number }> {
  return postJson('/api/admin/area-sweeps', { lat, lng, km })
}

export function fetchCurrentSweep(): Promise<SweepOut> {
  return getJson<SweepOut>('/api/admin/area-sweeps/current')
}
