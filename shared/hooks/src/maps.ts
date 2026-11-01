/**
 * Map / address-search client.
 *
 * All provider keys live on the server; the browser only calls `/api/map/*`.
 * `SchemaForm` LOCATION fields use these helpers through `LocationField.vue`.
 */

import { get, put } from './http'

export type MapProviderId = 'tianditu' | 'amap' | 'baidu' | 'google'

export type MapProviderInfo = {
  id: MapProviderId | string
  label: string
  configured: boolean
}

export type MapConfig = {
  provider: string
  providers: MapProviderInfo[]
  configured: boolean
  crs: string
}

/** Global-settings map section (`provider` + up to two tokens). */
export type MapSettings = {
  provider: string
  token1: string
  token2: string
}

export type MapSettingsPayload = MapConfig & {
  settings: MapSettings
  canEdit: boolean
  token1Set: boolean
  token2Set: boolean
}

export type PlaceResult = {
  id: string
  name: string
  address: string
  label: string
  lat: number
  lng: number
  provider: string
  crs: string
}

export type PlaceSearchResult = {
  query: string
  provider: string
  label: string
  crs: string
  results: PlaceResult[]
}

export type PlaceSearchOptions = {
  provider?: string
  region?: string
  limit?: number
}

export type StaticMapOptions = {
  zoom?: number
  width?: number
  height?: number
}

const EMPTY_SEARCH: PlaceSearchResult = {
  query: '',
  provider: '',
  label: '',
  crs: '',
  results: [],
}

let configCache: MapConfig | null = null
let configRequest: Promise<MapConfig> | null = null

/** Cached `/api/map/config`; pass `force` after changing map settings. */
export function loadMapConfig(force = false): Promise<MapConfig> {
  if (!force && configCache) return Promise.resolve(configCache)
  if (!force && configRequest) return configRequest
  const req = get<MapConfig>('/api/map/config').then((cfg) => {
    configCache = cfg
    return cfg
  })
  configRequest = req
  req.then(
    () => {
      if (configRequest === req) configRequest = null
    },
    () => {
      if (configRequest === req) configRequest = null
    },
  )
  return req
}

/** Drop the cached provider list (tests / after server restart). */
export function clearMapConfigCache(): void {
  configCache = null
  configRequest = null
}

/** Load map settings for the global-settings page. */
export function loadMapSettings(): Promise<MapSettingsPayload> {
  return get<MapSettingsPayload>('/api/map/settings')
}

/** Save `provider/token1/token2`; omitted tokens keep their stored value. */
export async function saveMapSettings(
  settings: Partial<MapSettings>,
): Promise<MapSettingsPayload> {
  const payload = await put<MapSettingsPayload>('/api/map/settings', settings)
  clearMapConfigCache()
  return payload
}

export function searchPlaces(
  query: string,
  options: PlaceSearchOptions = {},
): Promise<PlaceSearchResult> {
  const q = String(query || '').trim()
  if (!q) return Promise.resolve(EMPTY_SEARCH)
  const params = new URLSearchParams({ q })
  if (options.provider) params.set('provider', options.provider)
  if (options.region) params.set('region', options.region)
  if (options.limit) params.set('limit', String(options.limit))
  return get<PlaceSearchResult>(`/api/map/search?${params.toString()}`)
}

/** `<img src>` for a marker map; the server proxies the provider image. */
export function staticMapUrl(
  lat: number,
  lng: number,
  options: StaticMapOptions = {},
): string {
  const params = new URLSearchParams({
    lat: String(lat),
    lng: String(lng),
  })
  if (options.zoom) params.set('zoom', String(options.zoom))
  if (options.width) params.set('width', String(options.width))
  if (options.height) params.set('height', String(options.height))
  return `/api/map/static?${params.toString()}`
}
