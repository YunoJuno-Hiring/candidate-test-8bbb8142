import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DeveloperSettings from './DeveloperSettings'
import { ApiError, CreatedWebhookEndpoint, WebhookEndpoint } from '../api/client'
import { createWebhookEndpoint, deleteWebhookEndpoint, fetchWebhookEndpoints } from '../api/webhooks'
import { renderRoute } from '../test/render'

vi.mock('../api/webhooks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/webhooks')>()),
  fetchWebhookEndpoints: vi.fn(),
  createWebhookEndpoint: vi.fn(),
  deleteWebhookEndpoint: vi.fn(),
}))

const SECRET = 'a'.repeat(64)

function makeEndpoint(overrides: Partial<WebhookEndpoint> = {}): WebhookEndpoint {
  return {
    id: 1,
    url: 'http://webhook-receiver:8027/hook',
    active: true,
    event_types: [],
    created_at: '2026-10-01T10:00:00Z',
    last_modified: '2026-10-01T10:00:00Z',
    ...overrides,
  }
}

function renderPage() {
  return renderRoute(<DeveloperSettings />, { path: '/developers', route: '/developers' })
}

describe('DeveloperSettings', () => {
  beforeEach(() => {
    vi.mocked(fetchWebhookEndpoints).mockResolvedValue([])
  })

  it('offers every subscribable event type except webhook.test', () => {
    renderPage()

    const picker = screen.getByRole('group', { name: 'Events' })
    const labels = within(picker)
      .getAllByRole('checkbox')
      .map((checkbox) => checkbox.closest('label')?.textContent)
    expect(labels).toEqual(['Timesheet submitted', 'Timesheet approved', 'Contract created'])
    expect(screen.queryByText(/Test event/)).not.toBeInTheDocument()
  })

  it('creates an endpoint with the selected event types and shows the secret once', async () => {
    const user = userEvent.setup()
    const created: CreatedWebhookEndpoint = {
      ...makeEndpoint({ id: 7, event_types: ['contract.created', 'timesheet.approved'] }),
      secret: SECRET,
    }
    vi.mocked(createWebhookEndpoint).mockResolvedValue(created)
    renderPage()

    await user.type(screen.getByLabelText('Destination URL'), created.url)
    await user.click(screen.getByRole('checkbox', { name: /Timesheet approved/ }))
    await user.click(screen.getByRole('checkbox', { name: /Contract created/ }))
    vi.mocked(fetchWebhookEndpoints).mockResolvedValue([makeEndpoint(created)])
    await user.click(screen.getByRole('button', { name: 'Save endpoint' }))

    expect(createWebhookEndpoint).toHaveBeenCalledWith({
      url: created.url,
      event_types: ['timesheet.approved', 'contract.created'],
    })
    expect(await screen.findByLabelText('Signing secret')).toHaveTextContent(SECRET)
    expect(screen.getByLabelText('Destination URL')).toHaveValue('')
    expect(screen.getByRole('checkbox', { name: /Contract created/ })).not.toBeChecked()

    await user.click(screen.getByRole('button', { name: "I've stored the secret" }))
    expect(screen.queryByText(SECRET)).not.toBeInTheDocument()
  })

  it('subscribes to every event when no event type is selected', async () => {
    const user = userEvent.setup()
    vi.mocked(createWebhookEndpoint).mockResolvedValue({ ...makeEndpoint(), secret: SECRET })
    renderPage()

    await user.type(screen.getByLabelText('Destination URL'), 'https://example.com/hook')
    await user.click(screen.getByRole('button', { name: 'Save endpoint' }))

    expect(createWebhookEndpoint).toHaveBeenCalledWith({ url: 'https://example.com/hook', event_types: [] })
  })

  it('shows the backend validation message when saving fails', async () => {
    const user = userEvent.setup()
    vi.mocked(createWebhookEndpoint).mockRejectedValue(
      new ApiError(400, { url: ['This URL is already registered for your company.'] }),
    )
    renderPage()

    await user.type(screen.getByLabelText('Destination URL'), 'https://example.com/hook')
    await user.click(screen.getByRole('button', { name: 'Save endpoint' }))

    expect(await screen.findByText('This URL is already registered for your company.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Signing secret')).not.toBeInTheDocument()
  })

  it('lists configured endpoints without their secrets', async () => {
    vi.mocked(fetchWebhookEndpoints).mockResolvedValue([
      makeEndpoint({ id: 1, url: 'https://a.example.com/hook' }),
      makeEndpoint({ id: 2, url: 'https://b.example.com/hook', active: false, event_types: ['timesheet.submitted'] }),
    ])
    renderPage()

    const rows = await screen.findAllByRole('row')
    expect(rows).toHaveLength(3)
    expect(within(rows[1]).getByText('https://a.example.com/hook')).toBeInTheDocument()
    expect(within(rows[1]).getByText('All events')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Timesheet submitted')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Disabled')).toBeInTheDocument()
    expect(document.body).not.toHaveTextContent('timesheet.submitted')
    expect(screen.queryByLabelText('Signing secret')).not.toBeInTheDocument()
  })

  it('shows an empty state when there are no endpoints', async () => {
    renderPage()

    expect(await screen.findByText('No webhook destinations configured.')).toBeInTheDocument()
  })

  it('navigates to the webhook detail page when a row is clicked', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchWebhookEndpoints).mockResolvedValue([makeEndpoint({ id: 42 })])
    renderPage()

    await user.click(await screen.findByText('All events'))

    expect(screen.getByTestId('location')).toHaveTextContent('/developers/webhook/42')
  })

  it('deletes an endpoint only after confirmation', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchWebhookEndpoints).mockResolvedValue([makeEndpoint({ id: 5 })])
    vi.mocked(deleteWebhookEndpoint).mockResolvedValue(undefined)
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Delete webhook/ }))

    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('Are you sure you want to delete this webhook?')
    expect(deleteWebhookEndpoint).not.toHaveBeenCalled()
    expect(screen.queryByTestId('location')).not.toBeInTheDocument()

    vi.mocked(fetchWebhookEndpoints).mockResolvedValue([])
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    expect(deleteWebhookEndpoint).toHaveBeenCalledWith(5)
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(await screen.findByText('No webhook destinations configured.')).toBeInTheDocument()
  })

  it('keeps the endpoint when deletion is cancelled', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchWebhookEndpoints).mockResolvedValue([makeEndpoint()])
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Delete webhook/ }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(deleteWebhookEndpoint).not.toHaveBeenCalled()
    expect(screen.getByRole('link', { name: 'http://webhook-receiver:8027/hook' })).toBeInTheDocument()
  })

  it('keeps the dialog open with an error when deletion fails', async () => {
    const user = userEvent.setup()
    vi.mocked(fetchWebhookEndpoints).mockResolvedValue([makeEndpoint()])
    vi.mocked(deleteWebhookEndpoint).mockRejectedValue(new ApiError(500, {}))
    renderPage()

    await user.click(await screen.findByRole('button', { name: /Delete webhook/ }))
    await user.click(screen.getByRole('button', { name: 'Delete' }))

    const dialog = screen.getByRole('alertdialog')
    expect(await within(dialog).findByText('Failed to delete webhook. Please try again.')).toBeInTheDocument()
  })
})
