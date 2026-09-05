type ApiErrorBody = { detail?: string }

function retryAfterSeconds(response: Response): number | null {
  const raw = response.headers.get('Retry-After')?.trim()
  if (!raw) return null

  if (/^\d+(?:\.\d+)?$/.test(raw)) {
    const seconds = Number(raw)
    return Number.isFinite(seconds) ? Math.max(0, Math.ceil(seconds)) : null
  }

  const retryAt = Date.parse(raw)
  if (Number.isNaN(retryAt)) return null
  return Math.max(0, Math.ceil((retryAt - Date.now()) / 1000))
}

export async function responseErrorMessage(response: Response, fallback?: string): Promise<string> {
  let message = fallback ?? `HTTP ${response.status}`
  try {
    const body = await response.json() as ApiErrorBody
    if (body.detail) message = body.detail
  } catch {
    // Сервер мог вернуть ответ без JSON.
  }

  if (response.status !== 429) return message

  const retryAfter = retryAfterSeconds(response)
  const base = message === 'HTTP 429' ? 'Слишком много запросов' : message.replace(/[.\s]+$/, '')
  return retryAfter === null
    ? `${base}. Повторите позже.`
    : `${base}. Повторите через ${retryAfter} с.`
}
