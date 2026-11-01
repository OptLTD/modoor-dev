/**
 * LOCATION field value format (shared with the mobile app).
 *
 * Wire format: ``display|lat,lng|address|`` — four Simplify fields separated by
 * ``|``. The mobile `LocationInput.vue` uses the same layout:
 *   first  = display name (POI / short label)
 *   second = "lat,lng" (latitude first)
 *   third  = detailed address
 *   latest = reserved
 *
 * Empty trailing fields are omitted, so a picked POI is usually stored as
 * ``"连云港站|34.61008,119.15742|人民东路1"``. Plain text (legacy/manual input)
 * is still accepted and returned unchanged by `formatLocationValue`.
 */

export type LocationValue = {
  display: string
  address: string
  lat?: number
  lng?: number
}

const FIELD_FENCE = '|'

export function parseLocationValue(raw: string | null | undefined): LocationValue {
  const text = String(raw ?? '')
  if (!text) return { display: '', address: '' }
  const parts = text.split(FIELD_FENCE)
  const first = (parts[0] || '').trim()
  const second = (parts[1] || '').trim()
  const third = (parts[2] || '').trim()

  let lat: number | undefined
  let lng: number | undefined
  if (second) {
    const coords = second.split(',')
    if (coords.length >= 2) {
      const nextLat = Number(coords[0].trim())
      const nextLng = Number(coords[1].trim())
      if (Number.isFinite(nextLat) && Number.isFinite(nextLng)) {
        lat = nextLat
        lng = nextLng
      }
    }
  }

  return {
    display: first || third,
    address: third || first,
    lat,
    lng,
  }
}

/** Text shown inside the input: first segment, falling back to the address. */
export function locationDisplayText(raw: string | null | undefined): string {
  return parseLocationValue(raw).display
}

export function formatLocationValue(value: LocationValue): string {
  const display = String(value.display || value.address || '').trim()
  const address = String(value.address || value.display || '').trim()
  const lat = Number(value.lat)
  const lng = Number(value.lng)
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    // No coordinates: store plain text so legacy/manual values stay untouched.
    return display || address
  }
  return [display, `${lat},${lng}`, address].join(FIELD_FENCE)
}
