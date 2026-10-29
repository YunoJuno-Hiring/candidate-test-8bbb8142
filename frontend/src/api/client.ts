export type UserRole = 'admin' | 'freelancer' | 'unknown'

export interface AuthUser {
  id: number
  email: string
  role: UserRole
}

export interface Company {
  id: number
  name: string
  billing_email: string
}

export interface FreelancerProfile {
  id: number
  name: string
}

export interface Contract {
  id: number
  company: Company
  freelancer: FreelancerProfile
  daily_rate: string
  start_date: string
  end_date: string
  status: 'active' | 'closed'
}

export interface TimesheetEntry {
  id: number
  contract: number
  contract_id: number
  date: string
  hours: string
  status: 'draft' | 'submitted' | 'approved' | 'rejected'
  rejection_reason: string | null
}

export interface BillingRunResult {
  run_id: string
  invoices_generated: number
  status: string
}

export interface Invoice {
  id: string | number
  [key: string]: unknown
}

// 'webhook.test' is not listed: it is sent on demand and cannot be subscribed to.
export type WebhookEventType = 'timesheet.submitted' | 'timesheet.approved' | 'contract.created'

export interface WebhookEndpoint {
  id: number
  url: string
  active: boolean
  // Empty means the endpoint receives every event type.
  event_types: WebhookEventType[]
  created_at: string
  last_modified: string
}

// Only the create response carries the secret; it is never returned again.
export interface CreatedWebhookEndpoint extends WebhookEndpoint {
  secret: string
}

export interface WebhookDelivery {
  id: number
  event_id: string
  event_type: WebhookEventType | 'webhook.test'
  attempt: number
  successful: boolean
  reason: string
  created_at: string
}

export interface WebhookEndpointDetail extends WebhookEndpoint {
  deliveries: WebhookDelivery[]
}

function getToken(): string | null {
  return localStorage.getItem('token')
}

function authHeaders(): HeadersInit {
  const token = getToken()
  return token ? { Authorization: `Token ${token}` } : {}
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(options.headers ?? {}),
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const err = new ApiError(res.status, body)
    throw err
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export class ApiError extends Error {
  status: number
  data: Record<string, unknown>

  constructor(status: number, data: Record<string, unknown>) {
    super(`HTTP ${status}`)
    this.status = status
    this.data = data
  }
}

export const api = {
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  get: <T>(path: string) => request<T>(path),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
