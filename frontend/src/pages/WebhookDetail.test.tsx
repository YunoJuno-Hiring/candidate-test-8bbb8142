import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import WebhookDetail from './WebhookDetail'
import { ApiError, WebhookDelivery, WebhookEndpointDetail } from '../api/client'
import { fetchWebhookEndpoint, sendTestWebhookEvent, updateWebhookEndpoint } from '../api/webhooks'
import { renderRoute } from '../test/render'

vi.mock('../api/webhooks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/webhooks')>()),
  fetchWebhookEndpoint: vi.fn(),
  sendTestWebhookEvent: vi.fn(),
  updateWebhookEndpoint: vi.fn(),
}))

function makeTestDelivery(overrides: Partial<WebhookDelivery> = {}): WebhookDelivery {
  return {
    id: 20,
    event_id: '0b6a2f1e-0000-4000-8000-000000000020',
    event_type: 'webhook.test',
    attempt: 1,
    successful: true,
    reason: 'HTTP 200',
    created_at: '2026-10-04T09:00:00Z',
    ...overrides,
  }
}

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

  it('sends a test event and shows it in the delivery log', async () => {
    const user = userEvent.setup()
    const delivery = makeTestDelivery()
    vi.mocked(fetchWebhookEndpoint)
      .mockResolvedValueOnce(makeDetail())
      .mockResolvedValue(makeDetail({ deliveries: [delivery] }))
    vi.mocked(sendTestWebhookEvent).mockResolvedValue(delivery)
    renderPage('3')

    await user.click(await screen.findByRole('button', { name: 'Send test event' }))

    expect(sendTestWebhookEvent).toHaveBeenCalledWith(3)
    expect(await screen.findByRole('status')).toHaveTextContent('Test event delivered (HTTP 200).')
    const [, row] = await screen.findAllByRole('row')
    expect(within(row).getByText('Test event')).toBeInTheDocument()
  })

  it('reports a test event the receiver rejected', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchWebhookEndpoint).mockResolvedValue(makeDetail())
    vi.mocked(sendTestWebhookEvent).mockResolvedValue(
      makeTestDelivery({ successful: false, reason: 'connection failed' }),
    )
    renderPage('3')

    await user.click(await screen.findByRole('button', { name: 'Send test event' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Test event failed: connection failed.')
  })

  it('deactivates the webhook and keeps its delivery log', async () => {
    const user = userEvent.setup()
    const { deliveries, ...endpoint } = makeDetail({ deliveries: [makeTestDelivery()] })
    vi.mocked(fetchWebhookEndpoint).mockResolvedValue({ ...endpoint, deliveries })
    vi.mocked(updateWebhookEndpoint).mockResolvedValue({ ...endpoint, active: false })
    renderPage('3')

    const toggle = await screen.findByRole('switch', { name: 'Active' })
    expect(toggle).toBeChecked()
    await user.click(toggle)

    expect(updateWebhookEndpoint).toHaveBeenCalledWith(3, { active: false })
    expect(await screen.findByText('Disabled')).toBeInTheDocument()
    expect(toggle).not.toBeChecked()
    expect(screen.getByText('Receives no events. Test events can still be sent.')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(2)
  })

  it('activates a disabled webhook', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchWebhookEndpoint).mockResolvedValue(makeDetail({ active: false }))
    vi.mocked(updateWebhookEndpoint).mockResolvedValue({ ...makeDetail(), active: true })
    renderPage('3')

    await user.click(await screen.findByRole('switch', { name: 'Active' }))

    expect(updateWebhookEndpoint).toHaveBeenCalledWith(3, { active: true })
    expect(await screen.findByText('Active')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Active' })).toBeChecked()
  })

  it('keeps the current state and shows an error when the update fails', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchWebhookEndpoint).mockResolvedValue(makeDetail())
    vi.mocked(updateWebhookEndpoint).mockRejectedValue(new ApiError(500, {}))
    renderPage('3')

    await user.click(await screen.findByRole('switch', { name: 'Active' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to update the webhook.')
    expect(screen.getByRole('switch', { name: 'Active' })).toBeChecked()
    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  it('shows an error when the test event request fails', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchWebhookEndpoint).mockResolvedValue(makeDetail())
    vi.mocked(sendTestWebhookEvent).mockRejectedValue(new ApiError(500, {}))
    renderPage('3')

    await user.click(await screen.findByRole('button', { name: 'Send test event' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not send the test event.')
    expect(screen.getByRole('button', { name: 'Send test event' })).toBeEnabled()
  })
})
