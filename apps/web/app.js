const page = document.body.dataset.page || 'home'
const apiBaseUrl = String(window.APP_CONFIG?.apiBaseUrl || '').trim().replace(/\/$/, '')

const state = {
  summary: null,
  health: null,
  orders: [],
  selectedOrderNumber: null,
  selectedOrder: null,
  activeCallId: null,
  activeCall: null,
  transcript: [],
  calls: [],
  refreshHandles: []
}

function byId(id) {
  return document.getElementById(id)
}

async function fetchJson(url, options = {}) {
  const targetUrl = apiUrl(url)
  const headers = new Headers(options.headers || {})
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  try {
    const targetHost = new URL(targetUrl, window.location.origin).hostname
    if (targetHost.endsWith('ngrok-free.dev')) {
      headers.set('ngrok-skip-browser-warning', 'true')
    }
  } catch (error) {
    console.warn('Unable to inspect request host', error)
  }
  const response = await fetch(targetUrl, {
    ...options,
    headers
  })
  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed: ${response.status}`)
  }
  return payload
}

function apiUrl(path) {
  if (!apiBaseUrl) {
    return path
  }
  if (/^https?:\/\//.test(path)) {
    return path
  }
  return `${apiBaseUrl}${path}`
}

function formatCurrency(value) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD'
  }).format(Number(value || 0))
}

function formatLongDate() {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  }).format(new Date())
}

function formatTime(value) {
  if (!value) return '--'
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit'
  }).format(new Date(value))
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function getOrderParam() {
  return new URL(window.location.href).searchParams.get('order')
}

function buildCaseUrl(orderNumber) {
  const url = new URL('/cases.html', window.location.origin)
  if (orderNumber) {
    url.searchParams.set('order', orderNumber)
  }
  return `${url.pathname}${url.search}`
}

function writeOrderParam(orderNumber) {
  const url = new URL(window.location.href)
  if (orderNumber) {
    url.searchParams.set('order', orderNumber)
  } else {
    url.searchParams.delete('order')
  }
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
}

function scheduleRefresh(intervalMs, callback) {
  const handle = window.setInterval(async () => {
    if (document.hidden) return
    try {
      await callback()
    } catch (error) {
      handleError(error)
    }
  }, intervalMs)
  state.refreshHandles.push(handle)
}

function clearRefreshes() {
  for (const handle of state.refreshHandles) {
    window.clearInterval(handle)
  }
  state.refreshHandles = []
}

function handleError(error) {
  console.error(error)
  const message = error instanceof Error ? error.message : String(error)
  if (page === 'case') {
    const statusNode = byId('override-status')
    if (statusNode) {
      statusNode.textContent = message
    }
  }
}

function setStatusTone(node, status) {
  if (!node) return
  const normalized = String(status || 'idle').toLowerCase().replaceAll('_', '-')
  node.className = node.className
    .split(' ')
    .filter((item) => !item.startsWith('status-'))
    .concat(`status-${normalized}`)
    .join(' ')
  node.textContent = status || 'Idle'
}

function renderModeLabel() {
  const mode = state.health?.mode || state.summary?.mode || 'local'
  const projectName = state.health?.project_name || 'ecommerce'
  return `${String(mode).toUpperCase()} / ${projectName}`
}

function renderRuntimeLabel() {
  const transport = String(state.health?.call_transport || 'simulation').toUpperCase()
  const backend = String(state.health?.agent_backend || 'deterministic').replaceAll('_', ' ').toUpperCase()
  return `${transport} / ${backend}`
}

function renderRuntimeDetail() {
  const stt = state.health?.whisper_model || 'whisper-1'
  const tts = state.health?.tts_provider || 'openai'
  return `STT ${stt} · TTS ${tts}`
}

async function loadSummaryAndHealth() {
  const [summary, health] = await Promise.all([
    fetchJson('/api/summary'),
    fetchJson('/api/health')
  ])
  state.summary = summary
  state.health = health
}

async function loadOrders({ status = null, limit = 50 } = {}) {
  const url = new URL(apiUrl('/api/orders'), window.location.origin)
  url.searchParams.set('limit', String(limit))
  if (status) {
    url.searchParams.set('status', status)
  }
  const response = await fetchJson(`${url.pathname}${url.search}${url.hash}`)
  state.orders = response.items || []
}

async function loadCalls(limit = 20) {
  const response = await fetchJson(`/api/calls?limit=${limit}`)
  state.calls = response.items || []
}

async function fetchOrder(orderNumber) {
  state.selectedOrder = await fetchJson(`/api/orders/${orderNumber}`)
}

function pickCallIdForOrder(orderNumber) {
  if (!orderNumber) return null
  const matching = state.calls.filter((call) => call.order_number === orderNumber)
  const inProgress = matching.find((call) => call.status === 'in_progress')
  const queued = matching.find((call) => call.status === 'queued')
  return inProgress?.call_id || queued?.call_id || state.selectedOrder?.last_call_id || matching[0]?.call_id || null
}

async function refreshActiveCall() {
  if (!state.activeCallId) {
    state.activeCall = null
    state.transcript = []
    return
  }

  try {
    const [call, transcriptResponse] = await Promise.all([
      fetchJson(`/api/calls/${state.activeCallId}`),
      fetchJson(`/api/calls/${state.activeCallId}/transcript`)
    ])
    state.activeCall = call
    state.transcript = transcriptResponse.items || []
  } catch (error) {
    state.activeCall = null
    state.activeCallId = null
    state.transcript = []
    throw error
  }
}

function renderHomeHeader() {
  byId('today-date').textContent = formatLongDate()
  byId('mode-pill').textContent = renderModeLabel()
  byId('summary-problematic').textContent = state.summary?.orders?.problematic ?? '--'
  byId('summary-refunded').textContent = state.summary?.orders?.refunded ?? '--'
  byId('summary-live-calls').textContent = state.summary?.calls?.in_progress ?? '--'
  byId('summary-runtime').textContent = renderRuntimeLabel()
  byId('summary-runtime-detail').textContent = renderRuntimeDetail()

  const firstOrder = state.orders[0]?.order_number || ''
  byId('open-cases-cta').setAttribute('href', buildCaseUrl(firstOrder))
}

function attachHomeOrderActions() {
  document.querySelectorAll('[data-open-case]').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.stopPropagation()
      const orderNumber = button.getAttribute('data-open-case')
      if (orderNumber) {
        window.location.href = buildCaseUrl(orderNumber)
      }
    })
  })
}

function renderHomeOrders() {
  const body = byId('home-orders-body')
  const rows = state.orders

  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="5">No problem cases are currently queued.</td></tr>'
    return
  }

  body.innerHTML = rows
    .map(
      (order) => `
        <tr class="row-clickable" data-row-order="${escapeHtml(order.order_number)}">
          <td>
            <div class="row-title">${escapeHtml(order.order_number)}</div>
            <div class="fact-label">${escapeHtml(order.shipping_city)}, ${escapeHtml(order.shipping_state)}</div>
          </td>
          <td>
            ${escapeHtml(order.customer_name)}<br>
            <span class="fact-label">${escapeHtml(order.customer_phone)}</span>
          </td>
          <td>${escapeHtml(order.issue_reason)}</td>
          <td>${formatCurrency(order.refund_amount)}</td>
          <td><button class="table-action" type="button" data-open-case="${escapeHtml(order.order_number)}">Open Case</button></td>
        </tr>
      `
    )
    .join('')

  body.querySelectorAll('[data-row-order]').forEach((row) => {
    row.addEventListener('click', () => {
      const orderNumber = row.getAttribute('data-row-order')
      if (orderNumber) {
        window.location.href = buildCaseUrl(orderNumber)
      }
    })
  })

  attachHomeOrderActions()
}

function attachHomeCallActions() {
  document.querySelectorAll('[data-open-call-order]').forEach((button) => {
    button.addEventListener('click', () => {
      const orderNumber = button.getAttribute('data-open-call-order')
      if (orderNumber) {
        window.location.href = buildCaseUrl(orderNumber)
      }
    })
  })
}

function renderHomeCalls() {
  const list = byId('home-call-list')
  if (!state.calls.length) {
    list.innerHTML = '<li>No calls have been placed yet.</li>'
    return
  }

  list.innerHTML = state.calls
    .slice(0, 6)
    .map(
      (call) => `
        <li>
          <div class="activity-entry">
            <div class="activity-copy">
              <strong>${escapeHtml(call.order_number)}</strong><br>
              <span>${escapeHtml(call.customer_name)} · ${escapeHtml(call.status)}</span><br>
              <span class="fact-label">${formatTime(call.updated_at || call.created_at)}</span>
            </div>
            <button class="table-action" type="button" data-open-call-order="${escapeHtml(call.order_number)}">Open Case</button>
          </div>
        </li>
      `
    )
    .join('')

  attachHomeCallActions()
}

async function bootstrapAndRefresh(loader) {
  await fetchJson('/api/admin/bootstrap', { method: 'POST' })
  await loader()
}

async function refreshHomePage() {
  await Promise.all([
    loadSummaryAndHealth(),
    loadOrders({ status: 'problematic', limit: 24 }),
    loadCalls(8)
  ])
  renderHomeHeader()
  renderHomeOrders()
  renderHomeCalls()
}

async function initHomePage() {
  byId('bootstrap-btn').addEventListener('click', async () => {
    await bootstrapAndRefresh(refreshHomePage)
  })

  await refreshHomePage()
}

function renderCaseHeader() {
  byId('workspace-date').textContent = formatLongDate()
  byId('workspace-mode-pill').textContent = `${renderModeLabel()} / ${renderRuntimeLabel()}`
}

function renderCaseOrder() {
  const order = state.selectedOrder
  const title = byId('detail-title')
  const facts = byId('order-facts')
  const itemList = byId('item-list')

  if (!order) {
    title.textContent = 'Awaiting selection'
    facts.className = 'facts-grid empty-state'
    facts.textContent = 'Open a problem case from the home page to inspect the customer record and prepare the live call.'
    itemList.innerHTML = ''
    return
  }

  title.textContent = `${order.order_number} / ${order.customer_name}`
  facts.className = 'facts-grid'
  const factRows = [
    ['Status', order.fulfillment_status],
    ['Issue', order.issue_reason],
    ['Refund', formatCurrency(order.refund_amount)],
    ['Phone', order.customer_phone],
    ['Email', order.customer_email],
    ['Ship To', `${order.shipping_city}, ${order.shipping_state} ${order.shipping_postal_code}`]
  ]
  facts.innerHTML = factRows
    .map(
      ([label, value]) => `
        <div class="fact">
          <div class="fact-label">${escapeHtml(label)}</div>
          <div class="fact-value">${escapeHtml(value)}</div>
        </div>
      `
    )
    .join('')

  itemList.innerHTML = (order.items || [])
    .map(
      (item) => `
        <li>
          <strong>${escapeHtml(item.quantity)}x ${escapeHtml(item.product_name)}</strong><br>
          <span class="fact-label">${escapeHtml(item.sku)} / ${formatCurrency(item.line_total)}</span>
        </li>
      `
    )
    .join('')
}

function renderCaseControls() {
  const startCallButton = byId('start-call-btn')
  const overrideText = byId('override-text')
  const armButton = byId('arm-override-btn')
  const overrideStatus = byId('override-status')
  const callStatePill = byId('call-state-pill')
  const supportOrderContext = byId('support-order-context')

  const hasOrder = Boolean(state.selectedOrder)
  const hasLiveCapableCall =
    Boolean(state.activeCall) && !['completed', 'failed'].includes(String(state.activeCall.status || '').toLowerCase())
  const hasQueuedLine = Boolean(state.activeCall?.armed_override)
  const hasDraft = Boolean(overrideText.value.trim())
  const activeCallForOrder =
    Boolean(state.activeCall && state.activeCall.order_number === state.selectedOrderNumber) &&
    !['completed', 'failed'].includes(String(state.activeCall?.status || '').toLowerCase())

  startCallButton.disabled = !hasOrder || activeCallForOrder
  startCallButton.textContent = activeCallForOrder ? 'Call Active' : 'Call Customer'

  armButton.disabled = !(hasLiveCapableCall && hasDraft)
  armButton.textContent = 'Say'
  supportOrderContext.textContent = hasOrder
    ? `Selected order: ${state.selectedOrder.order_number}`
    : 'Selected order: --'
  overrideText.placeholder = hasOrder
    ? `Type the next line you want the agent to speak about order ${state.selectedOrder.order_number}...`
    : 'Type the next line you want the agent to speak about this order...'

  setStatusTone(callStatePill, state.activeCall?.status || 'Idle')

  if (!state.activeCallId) {
    overrideStatus.textContent = 'Start a call to send a live support prompt.'
  } else if (hasQueuedLine) {
    overrideStatus.textContent = `Queued next prompt: ${state.activeCall.armed_override}`
  } else if (hasLiveCapableCall) {
    overrideStatus.textContent = 'No prompt is queued. Type one line and send it before the next agent turn.'
  } else {
    overrideStatus.textContent = 'This call is no longer live. Start another call to send support guidance.'
  }
}

function renderCaseTranscript() {
  const title = byId('call-title')
  const status = byId('call-status')
  const reference = byId('refund-reference')
  const transcriptList = byId('transcript-list')

  if (!state.activeCall) {
    title.textContent = state.selectedOrderNumber
      ? `${state.selectedOrderNumber} / No call selected`
      : 'No active call'
    setStatusTone(status, 'Idle')
    reference.textContent = 'Ref: --'
    transcriptList.innerHTML = '<li><div class="speaker-tag">system</div><div>No live transcript is available yet.</div></li>'
    return
  }

  title.textContent = `${state.activeCall.order_number} / ${state.activeCall.customer_name}`
  setStatusTone(status, state.activeCall.status || 'Idle')
  reference.textContent = `Ref: ${state.activeCall.refund_reference || '--'}`

  if (!state.transcript.length) {
    transcriptList.innerHTML = '<li><div class="speaker-tag">system</div><div>The call has started, but no transcript turns have arrived yet.</div></li>'
    return
  }

  transcriptList.innerHTML = state.transcript
    .map(
      (turn) => `
        <li>
          <div class="speaker-tag speaker-${escapeHtml(turn.speaker)}">${escapeHtml(turn.speaker)}</div>
          <div>${escapeHtml(turn.text)}</div>
        </li>
      `
    )
    .join('')
}

async function selectOrder(orderNumber, { preferredCallId = null } = {}) {
  state.selectedOrderNumber = orderNumber
  writeOrderParam(orderNumber)
  await fetchOrder(orderNumber)
  state.activeCallId = preferredCallId || pickCallIdForOrder(orderNumber)
  await refreshActiveCall()
  renderCaseOrder()
  renderCaseControls()
  renderCaseTranscript()
}

async function refreshCaseOverview() {
  await Promise.all([
    loadSummaryAndHealth(),
    loadOrders({ limit: 60 }),
    loadCalls(24)
  ])

  renderCaseHeader()

  if (!state.selectedOrderNumber) {
    state.selectedOrderNumber = getOrderParam() || state.orders.find((order) => order.fulfillment_status === 'problematic')?.order_number || null
  }

  if (!state.selectedOrderNumber) {
    renderCaseOrder()
    renderCaseControls()
    renderCaseTranscript()
    return
  }

  await selectOrder(state.selectedOrderNumber, { preferredCallId: state.activeCallId })
}

async function refreshCaseConversation() {
  if (!state.selectedOrderNumber) return
  if (!state.activeCallId) return
  if (['completed', 'failed'].includes(String(state.activeCall?.status || '').toLowerCase())) return

  const previousStatus = String(state.activeCall?.status || '').toLowerCase()
  state.activeCallId = pickCallIdForOrder(state.selectedOrderNumber) || state.activeCallId
  await refreshActiveCall()

  const currentStatus = String(state.activeCall?.status || '').toLowerCase()
  if (currentStatus !== previousStatus && ['completed', 'failed'].includes(currentStatus)) {
    await fetchOrder(state.selectedOrderNumber)
  }

  renderCaseOrder()
  renderCaseControls()
  renderCaseTranscript()
}

async function startCall() {
  if (!state.selectedOrderNumber) return
  const payload = {
    order_number: state.selectedOrderNumber,
    operator_name: 'city-desk'
  }
  const call = await fetchJson('/api/calls/outbound', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
  state.activeCallId = call.call_id
  await refreshCaseOverview()
}

async function queueSupportLine() {
  if (!state.activeCallId) return
  const textarea = byId('override-text')
  const text = textarea.value.trim()
  if (!text) return

  await fetchJson(`/api/calls/${state.activeCallId}/next-turn`, {
    method: 'POST',
    body: JSON.stringify({ text })
  })

  textarea.value = ''
  await refreshCaseConversation()
}

async function initCasePage() {
  byId('case-bootstrap-btn').addEventListener('click', async () => {
    await bootstrapAndRefresh(refreshCaseOverview)
  })
  byId('start-call-btn').addEventListener('click', startCall)
  byId('arm-override-btn').addEventListener('click', queueSupportLine)
  byId('override-text').addEventListener('input', renderCaseControls)
  byId('override-text').addEventListener('keydown', async (event) => {
    if (event.key !== 'Enter') return
    event.preventDefault()
    if (byId('arm-override-btn').disabled) return
    await queueSupportLine()
  })

  await refreshCaseOverview()
  scheduleRefresh(2800, refreshCaseConversation)
}

async function init() {
  window.addEventListener('beforeunload', clearRefreshes)

  if (page === 'case') {
    await initCasePage()
    return
  }

  await initHomePage()
}

init().catch(handleError)
