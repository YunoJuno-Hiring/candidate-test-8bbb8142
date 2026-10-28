import { screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import WebhookDetail from './WebhookDetail'
import { ApiError, WebhookEndpointDetail } from '../api/client'
import { fetchWebhookEndpoint } from '../api/webhooks'
import { renderRoute } from '../test/render'

vi.mock('../api/webhooks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/webhooks')>()),
  fetchWebhookEndpoint: vi.fn(),
}))

function makeDetail(overrides: Partial<WebhookEndpointDetail> = {}): WebhookEndpointDetail {
  return {
    id: 3,
    url: 'https://example.com/hook',
    active: true,
    event_types: ['timesheet.approved'],
    created_at: '2026-10-01T10:00:00Z',
    last_modified: '2026-10-02T10:00:00Z',
    deliveries: [],
    ...overrides,
  }
}

function renderPage(id: string) {
  return renderRoute(<WebhookDetail />, { path: '/developers/webhook/:id', route: `/developers/webhook/${id}` })
}

describe('WebhookDetail', () => {
  it('shows the endpoint and its delivery attempts', async () => {
    vi.mocked(fetchWebhookEndpoint).mockResolvedValue(
      makeDetail({
        deliveries: [
          {
            id: 12,
            event_id: '0b6a2f1e-0000-4000-8000-000000000002',
            event_type: 'webhook.test',
            attempt: 1,
            successful: true,
            reason: '',
            created_at: '2026-10-03T11:00:00Z',
          },
          {
            id: 11,
            event_id: '0b6a2f1e-0000-4000-8000-000000000001',
            event_type: 'timesheet.approved',
            attempt: 2,
            successful: true,
            reason: '',
            created_at: '2026-10-03T10:05:00Z',
          },
          {
            id: 10,
            event_id: '0b6a2f1e-0000-4000-8000-000000000001',
            event_type: 'timesheet.approved',
            attempt: 1,
            successful: false,
            reason: 'HTTP 500',
            created_at: '2026-10-03T10:00:00Z',
          },
        ],
      }),
    )
    renderPage('3')

    expect(await screen.findByRole('heading', { name: 'https://example.com/hook' })).toBeInTheDocument()
    expect(fetchWebhookEndpoint).toHaveBeenCalledWith(3)
    expect(screen.getByText('Active')).toBeInTheDocument()

    const [, testEvent, newest, oldest] = screen.getAllByRole('row')
    expect(within(testEvent).getByText('Test event')).toBeInTheDocument()
    expect(within(newest).getByText('Timesheet approved')).toBeInTheDocument()
    expect(within(newest).getByText('Delivered')).toBeInTheDocument()
    expect(within(newest).getByText('2')).toBeInTheDocument()
    expect(within(oldest).getByText('Failed')).toBeInTheDocument()
    expect(within(oldest).getByText('HTTP 500')).toBeInTheDocument()
    expect(document.body).not.toHaveTextContent(/timesheet\.approved|webhook\.test/)
  })

  it('shows an empty state when nothing has been delivered', async () => {
    vi.mocked(fetchWebhookEndpoint).mockResolvedValue(makeDetail({ event_types: [] }))
    renderPage('3')

    expect(await screen.findByText('No deliveries yet.')).toBeInTheDocument()
    expect(screen.getByText('All events')).toBeInTheDocument()
  })

  it('shows not found when the endpoint does not exist', async () => {
    vi.mocked(fetchWebhookEndpoint).mockRejectedValue(new ApiError(404, {}))
    renderPage('999')

    expect(await screen.findByText('Webhook not found')).toBeInTheDocument()
  })

  it('shows not found without calling the API for a non-numeric id', () => {
    renderPage('abc')

    expect(screen.getByText('Webhook not found')).toBeInTheDocument()
    expect(fetchWebhookEndpoint).not.toHaveBeenCalled()
  })

  it('shows an error for other failures', async () => {
    vi.mocked(fetchWebhookEndpoint).mockRejectedValue(new ApiError(500, {}))
    renderPage('3')

    expect(await screen.findByText('Failed to load webhook.')).toBeInTheDocument()
  })
})
