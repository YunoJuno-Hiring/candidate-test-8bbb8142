import { WebhookDelivery, WebhookEventType } from '../api/client'
import { eventTypeLabel } from '../api/webhooks'

export function EndpointStatusBadge({ isActive }: { isActive: boolean }) {
  const cls = isActive ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-500'
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {isActive ? 'Active' : 'Disabled'}
    </span>
  )
}

export function EventTypeTag({ eventType }: { eventType: WebhookDelivery['event_type'] }) {
  return (
    <span className="inline-block bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded text-xs">
      {eventTypeLabel(eventType)}
    </span>
  )
}

export function EventTypeTags({ eventTypes }: { eventTypes: WebhookEventType[] }) {
  if (eventTypes.length === 0) {
    return <span className="text-slate-500 text-xs">All events</span>
  }
  return (
    <div className="flex flex-wrap gap-1">
      {eventTypes.map((eventType) => (
        <EventTypeTag key={eventType} eventType={eventType} />
      ))}
    </div>
  )
}
