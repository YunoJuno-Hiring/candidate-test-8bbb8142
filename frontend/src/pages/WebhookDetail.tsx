import { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { fetchWebhookEndpoint, sendTestWebhookEvent } from '../api/webhooks'
import { ApiError, WebhookDelivery } from '../api/client'
import { EndpointStatusBadge, EventTypeTag, EventTypeTags } from '../components/WebhookBadges'

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString()
}

function BackLink() {
  return (
    <Link to="/developers" className="text-indigo-600 hover:text-indigo-800 text-sm mb-2 inline-block">
      ← Developer settings
    </Link>
  )
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-4 py-2">
      <dt className="w-32 shrink-0 text-slate-500">{label}</dt>
      <dd className="text-slate-800">{children}</dd>
    </div>
  )
}

function TestEventResult({ delivery, isRequestError }: { delivery?: WebhookDelivery; isRequestError: boolean }) {
  if (isRequestError) {
    return (
      <div role="alert" className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm">
        Could not send the test event. Please try again.
      </div>
    )
  }
  if (!delivery) return null

  if (delivery.successful) {
    return (
      <div role="status" className="bg-green-50 border border-green-200 text-green-800 rounded px-4 py-3 text-sm">
        Test event delivered ({delivery.reason}).
      </div>
    )
  }
  return (
    <div role="status" className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm">
      Test event failed: {delivery.reason || 'no response'}. Check that the URL is reachable from the YunoJuno
      server.
    </div>
  )
}

function DeliveryTable({ deliveries }: { deliveries: WebhookDelivery[] }) {
  if (deliveries.length === 0) {
    return (
      <div className="bg-white border border-slate-200 rounded-lg px-6 py-10 text-center">
        <p className="text-slate-500 text-sm">No deliveries yet.</p>
      </div>
    )
  }

  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 border-b border-slate-200">
          <tr>
            <th className="text-left px-4 py-3 font-medium text-slate-600">Sent</th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">Event</th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">Attempt</th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">Result</th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">Reason</th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">Event ID</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {deliveries.map((delivery) => (
            <tr key={delivery.id} className="hover:bg-slate-50">
              <td className="px-4 py-3 text-slate-700 whitespace-nowrap">{formatDateTime(delivery.created_at)}</td>
              <td className="px-4 py-3">
                <EventTypeTag eventType={delivery.event_type} />
              </td>
              <td className="px-4 py-3 text-slate-700">{delivery.attempt}</td>
              <td className="px-4 py-3">
                <span
                  className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${delivery.successful ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}
                >
                  {delivery.successful ? 'Delivered' : 'Failed'}
                </span>
              </td>
              <td className="px-4 py-3 text-slate-500 text-xs">{delivery.reason || '—'}</td>
              <td className="px-4 py-3 text-slate-500 font-mono text-xs">{delivery.event_id}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function WebhookDetail() {
  const { id } = useParams<{ id: string }>()
  const numId = Number(id)
  const isValidId = Number.isInteger(numId) && numId > 0

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['webhook-endpoint', numId],
    queryFn: () => fetchWebhookEndpoint(numId),
    enabled: isValidId,
    retry: false,
  })

  const queryClient = useQueryClient()
  const testMutation = useMutation({
    mutationFn: () => sendTestWebhookEvent(numId),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['webhook-endpoint', numId] }),
  })

  const isNotFound = !isValidId || (isError && error instanceof ApiError && error.status === 404)

  if (isNotFound) {
    return (
      <div>
        <BackLink />
        <div className="bg-white border border-slate-200 rounded-lg px-6 py-12 text-center max-w-md">
          <p className="text-slate-800 font-medium">Webhook not found</p>
          <p className="text-slate-500 text-sm mt-1">It may have been deleted.</p>
        </div>
      </div>
    )
  }

  if (isLoading) {
    return <p className="text-slate-500">Loading webhook…</p>
  }

  if (isError || !data) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm">
        Failed to load webhook.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <BackLink />
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-xl font-semibold text-slate-900 font-mono break-all">{data.url}</h1>
          <div className="flex items-center gap-3 shrink-0">
            <EndpointStatusBadge isActive={data.active} />
            <button
              type="button"
              onClick={() => testMutation.mutate()}
              disabled={testMutation.isPending}
              className="bg-indigo-600 text-white text-sm px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {testMutation.isPending ? 'Sending…' : 'Send test event'}
            </button>
          </div>
        </div>
      </div>

      <TestEventResult delivery={testMutation.data} isRequestError={testMutation.isError} />

      <dl className="bg-white border border-slate-200 rounded-lg px-6 py-2 text-sm divide-y divide-slate-100">
        <DetailRow label="Events">
          <EventTypeTags eventTypes={data.event_types} />
        </DetailRow>
        <DetailRow label="Created">{formatDateTime(data.created_at)}</DetailRow>
        <DetailRow label="Last modified">{formatDateTime(data.last_modified)}</DetailRow>
      </dl>

      <div>
        <h2 className="text-base font-medium text-slate-800 mb-1">Deliveries</h2>
        <p className="text-slate-500 text-xs mb-3">Most recent attempts first. Each retry is its own row.</p>
        <DeliveryTable deliveries={data.deliveries} />
      </div>
    </div>
  )
}
