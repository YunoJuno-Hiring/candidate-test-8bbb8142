import {
  api,
  CreatedWebhookEndpoint,
  WebhookDelivery,
  WebhookEndpoint,
  WebhookEndpointDetail,
  WebhookEventType,
} from './client'

// Mirrors DELIVERY_EVENT_TYPE_CHOICES in backend/webhooks/models.py.
const EVENT_TYPE_LABELS: Record<WebhookDelivery['event_type'], string> = {
  'timesheet.submitted': 'Timesheet submitted',
  'timesheet.approved': 'Timesheet approved',
  'contract.created': 'Contract created',
  'webhook.test': 'Test event',
}

const SUBSCRIBABLE_EVENT_TYPES: WebhookEventType[] = ['timesheet.submitted', 'timesheet.approved', 'contract.created']

export const WEBHOOK_EVENT_TYPES = SUBSCRIBABLE_EVENT_TYPES.map((value) => ({
  value,
  label: EVENT_TYPE_LABELS[value],
}))

export function eventTypeLabel(eventType: WebhookDelivery['event_type']): string {
  return EVENT_TYPE_LABELS[eventType]
}

export interface NewWebhookEndpointInput {
  url: string
  event_types: WebhookEventType[]
}

export function fetchWebhookEndpoints(): Promise<WebhookEndpoint[]> {
  return api.get('/api/webhook-endpoints/')
}

export function fetchWebhookEndpoint(id: number): Promise<WebhookEndpointDetail> {
  return api.get(`/api/webhook-endpoints/${id}/`)
}

export function createWebhookEndpoint(input: NewWebhookEndpointInput): Promise<CreatedWebhookEndpoint> {
  return api.post('/api/webhook-endpoints/', input)
}

export function updateWebhookEndpoint(
  id: number,
  changes: Partial<Pick<WebhookEndpoint, 'url' | 'active' | 'event_types'>>,
): Promise<WebhookEndpoint> {
  return api.patch(`/api/webhook-endpoints/${id}/`, changes)
}

// Resolves with the logged delivery whether or not the receiver accepted the event.
export function sendTestWebhookEvent(id: number): Promise<WebhookDelivery> {
  return api.post(`/api/webhook-endpoints/${id}/test/`, {})
}

export function deleteWebhookEndpoint(id: number): Promise<void> {
  return api.delete(`/api/webhook-endpoints/${id}/`)
}
