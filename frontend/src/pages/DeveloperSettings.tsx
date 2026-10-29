import { useState, FormEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import {
  fetchWebhookEndpoints,
  createWebhookEndpoint,
  deleteWebhookEndpoint,
  NewWebhookEndpointInput,
  WEBHOOK_EVENT_TYPES,
} from '../api/webhooks'
import { ApiError, CreatedWebhookEndpoint, WebhookEndpoint, WebhookEventType } from '../api/client'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EndpointStatusBadge, EventTypeTags } from '../components/WebhookBadges'

function firstFieldError(err: unknown): string | null {
  if (!(err instanceof ApiError) || err.status !== 400) return null
  for (const field of ['url', 'event_types', 'non_field_errors']) {
    const messages = err.data[field]
    if (Array.isArray(messages) && typeof messages[0] === 'string') return messages[0]
  }
  return null
}

function SecretNotice({ endpoint, onDismiss }: { endpoint: CreatedWebhookEndpoint; onDismiss: () => void }) {
  const [hasCopied, setHasCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(endpoint.secret)
      setHasCopied(true)
    } catch {
      setHasCopied(false)
    }
  }

  return (
    <div role="status" className="mt-4 bg-green-50 border border-green-200 rounded px-4 py-3 text-sm">
      <p className="text-green-800 font-medium">Endpoint saved: {endpoint.url}</p>
      <p className="text-green-800 mt-2">
        Copy the signing secret now. It is only shown once and cannot be retrieved later.
      </p>
      <div className="mt-2 flex items-center gap-2">
        <code
          aria-label="Signing secret"
          className="flex-1 bg-white border border-green-200 rounded px-2 py-1 font-mono text-xs text-slate-800 break-all"
        >
          {endpoint.secret}
        </code>
        <button
          type="button"
          onClick={handleCopy}
          className="text-xs px-3 py-1 rounded border border-green-300 text-green-800 hover:bg-green-100"
        >
          {hasCopied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="mt-3 text-xs text-green-800 underline hover:text-green-900"
      >
        I've stored the secret
      </button>
    </div>
  )
}

function EventTypePicker({
  selected,
  onChange,
}: {
  selected: WebhookEventType[]
  onChange: (next: WebhookEventType[]) => void
}) {
  function toggle(eventType: WebhookEventType) {
    onChange(
      selected.includes(eventType) ? selected.filter((t) => t !== eventType) : [...selected, eventType],
    )
  }

  return (
    <fieldset>
      <legend className="block text-sm font-medium text-slate-700 mb-1">Events</legend>
      <div className="space-y-1">
        {WEBHOOK_EVENT_TYPES.map(({ value, label }) => (
          <label key={value} className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={selected.includes(value)}
              onChange={() => toggle(value)}
              className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
            {label}
          </label>
        ))}
      </div>
      <p className="text-slate-400 text-xs mt-1">Leave all unchecked to receive every event.</p>
    </fieldset>
  )
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" className="w-4 h-4">
      <path
        fillRule="evenodd"
        d="M8.75 1A2.75 2.75 0 0 0 6 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 1 0 .23 1.482l.149-.022.841 10.518A2.75 2.75 0 0 0 7.596 19h4.807a2.75 2.75 0 0 0 2.742-2.53l.841-10.52.149.023a.75.75 0 0 0 .23-1.482A41.03 41.03 0 0 0 14 4.193V3.75A2.75 2.75 0 0 0 11.25 1h-2.5ZM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4ZM8.58 7.72a.75.75 0 0 0-1.5.06l.3 7.5a.75.75 0 1 0 1.5-.06l-.3-7.5Zm4.34.06a.75.75 0 1 0-1.5-.06l-.3 7.5a.75.75 0 1 0 1.5.06l.3-7.5Z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function EndpointTable({
  endpoints,
  onDelete,
}: {
  endpoints: WebhookEndpoint[]
  onDelete: (endpoint: WebhookEndpoint) => void
}) {
  const navigate = useNavigate()

  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 border-b border-slate-200">
          <tr>
            <th className="text-left px-4 py-3 font-medium text-slate-600">URL</th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">Events</th>
            <th className="text-left px-4 py-3 font-medium text-slate-600">Status</th>
            <th className="px-4 py-3">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {endpoints.map((ep) => (
            <tr
              key={ep.id}
              onClick={() => navigate(`/developers/webhook/${ep.id}`)}
              className="hover:bg-slate-50 cursor-pointer"
            >
              <td className="px-4 py-3 font-mono text-xs break-all">
                <Link
                  to={`/developers/webhook/${ep.id}`}
                  onClick={(e) => e.stopPropagation()}
                  className="text-indigo-600 hover:text-indigo-800"
                >
                  {ep.url}
                </Link>
              </td>
              <td className="px-4 py-3">
                <EventTypeTags eventTypes={ep.event_types} />
              </td>
              <td className="px-4 py-3">
                <EndpointStatusBadge isActive={ep.active} />
              </td>
              <td className="px-4 py-3 text-right">
                <button
                  type="button"
                  aria-label={`Delete webhook ${ep.url}`}
                  title="Delete webhook"
                  onClick={(e) => {
                    e.stopPropagation()
                    onDelete(ep)
                  }}
                  className="text-slate-400 hover:text-red-600 p-1 rounded"
                >
                  <TrashIcon />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function DeveloperSettings() {
  const [url, setUrl] = useState('')
  const [eventTypes, setEventTypes] = useState<WebhookEventType[]>([])
  const [createdEndpoint, setCreatedEndpoint] = useState<CreatedWebhookEndpoint | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<WebhookEndpoint | null>(null)
  const queryClient = useQueryClient()

  const endpointsQuery = useQuery({
    queryKey: ['webhook-endpoints'],
    queryFn: fetchWebhookEndpoints,
  })

  const createMutation = useMutation({
    mutationFn: (input: NewWebhookEndpointInput) => createWebhookEndpoint(input),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['webhook-endpoints'] })
      setCreatedEndpoint(data)
      setUrl('')
      setEventTypes([])
    },
    onError: (err) => {
      setErrorMsg(firstFieldError(err) ?? 'Failed to save endpoint. Please try again.')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteWebhookEndpoint(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ['webhook-endpoints'] })
      queryClient.removeQueries({ queryKey: ['webhook-endpoint', id] })
      if (createdEndpoint?.id === id) setCreatedEndpoint(null)
      setPendingDelete(null)
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setCreatedEndpoint(null)
    setErrorMsg(null)
    createMutation.mutate({ url, event_types: eventTypes })
  }

  function closeDeleteDialog() {
    setPendingDelete(null)
    deleteMutation.reset()
  }

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 mb-1">Developer settings</h1>
        <p className="text-slate-500 text-sm">
          Configure webhook endpoints to receive event notifications from YunoJuno.
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-6">
        <h2 className="text-base font-medium text-slate-800 mb-4">Add webhook destination</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="webhook-url" className="block text-sm font-medium text-slate-700 mb-1">
              Destination URL
            </label>
            <input
              id="webhook-url"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
              placeholder="https://example.com/webhook"
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <p className="text-slate-400 text-xs mt-1">
              For local testing, use{' '}
              <code className="bg-slate-100 px-1 rounded">http://localhost:8027/hook</code>
            </p>
          </div>
          <EventTypePicker selected={eventTypes} onChange={setEventTypes} />
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="bg-indigo-600 text-white text-sm px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {createMutation.isPending ? 'Saving…' : 'Save endpoint'}
          </button>
        </form>

        {createdEndpoint && (
          <SecretNotice endpoint={createdEndpoint} onDismiss={() => setCreatedEndpoint(null)} />
        )}
        {errorMsg && (
          <div className="mt-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded px-3 py-2">
            {errorMsg}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-base font-medium text-slate-800 mb-3">Configured endpoints</h2>

        {endpointsQuery.isLoading ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : endpointsQuery.isError ? (
          <p className="text-red-600 text-sm">Failed to load endpoints.</p>
        ) : !endpointsQuery.data || endpointsQuery.data.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-lg px-6 py-10 text-center">
            <p className="text-slate-500 text-sm">No webhook destinations configured.</p>
          </div>
        ) : (
          <EndpointTable endpoints={endpointsQuery.data} onDelete={setPendingDelete} />
        )}
      </div>

      {pendingDelete && (
        <ConfirmDialog
          title="Delete webhook"
          message="Are you sure you want to delete this webhook?"
          confirmLabel="Delete"
          isPending={deleteMutation.isPending}
          error={deleteMutation.isError ? 'Failed to delete webhook. Please try again.' : null}
          onConfirm={() => deleteMutation.mutate(pendingDelete.id)}
          onCancel={closeDeleteDialog}
        />
      )}
    </div>
  )
}
