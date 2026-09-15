const root = document.querySelector('#app')
const toastNode = document.querySelector('#toast')
document.querySelector('#close-window').onclick = () => { location.href = 'penguin-trade://close' }
const mediaOrigin = `${location.protocol}//media.localhost${location.port ? `:${location.port}` : ''}`
const requestedTarget = Number(new URLSearchParams(location.search).get('target')) || null
const requestedName = new URLSearchParams(location.search).get('name') || ''
const model = {
  token: sessionStorage.getItem('trade-token'),
  state: null,
  draft: new Map(),
  draftCoins: 0,
  tab: 'clothing',
  dirty: false,
  busy: false,
  lastTradeId: null,
}

const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
})[char])

function toast(message) {
  toastNode.textContent = message
  toastNode.classList.add('show')
  clearTimeout(toast.timer)
  toast.timer = setTimeout(() => toastNode.classList.remove('show'), 3200)
}

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  if (model.token) headers.Authorization = `Bearer ${model.token}`
  const result = await fetch(path, { ...options, headers })
  const body = await result.json().catch(() => ({}))
  if (!result.ok) {
    if (result.status === 401 && path !== '/api/login') logout(false)
    throw new Error(body.error || `Request failed (${result.status})`)
  }
  return body
}

function chrome(title, subtitle, body, actions = '') {
  return `<section class="shell">
    <header class="masthead"><div><h1>${escapeHtml(title)}</h1><p>${escapeHtml(subtitle)}</p></div>${actions}</header>
    <div class="content">${body}</div>
  </section>`
}

function renderLogin(error = '') {
  root.innerHTML = `<section class="shell login"><div class="content">
    <div class="logo-puck">↔</div><h2 style="text-align:center">Penguin Trading Post</h2>
    <p class="muted" style="text-align:center">Sign in with your game account. Your password is checked by the local server and is never stored here.</p>
    ${error ? `<div class="error">${escapeHtml(error)}</div>` : ''}
    <form id="login-form">
      <label for="username">Penguin name</label><input id="username" autocomplete="username" required maxlength="12">
      <label for="password">Password</label><input id="password" type="password" autocomplete="current-password" required>
      <button class="primary" style="width:100%;margin-top:20px" type="submit">Enter Trading Post</button>
    </form></div></section>`
  document.querySelector('#login-form').addEventListener('submit', login)
}

async function login(event) {
  event.preventDefault()
  const username = document.querySelector('#username').value
  const password = document.querySelector('#password').value
  try {
    const result = await api('/api/login', { method: 'POST', body: JSON.stringify({ username, password }) })
    model.token = result.token
    sessionStorage.setItem('trade-token', result.token)
    await refresh(true)
  } catch (error) { renderLogin(error.message) }
}

async function logout(callServer = true) {
  if (callServer && model.token) await api('/api/logout', { method: 'POST' }).catch(() => {})
  model.token = null
  model.state = null
  model.draft.clear()
  sessionStorage.removeItem('trade-token')
  renderLogin()
}

function renderLobby() {
  const { player, players } = model.state
  const selected = requestedTarget ? players.find(person => person.id === requestedTarget) : null
  const shownPlayers = selected ? [selected] : players
  const rows = shownPlayers.length ? shownPlayers.map(person => `<div class="player-row">
    <div><span class="status-dot ${person.busy ? 'busy' : ''}"></span><strong>${escapeHtml(person.nickname)}</strong>
      <div class="muted">${person.busy ? 'Already trading' : 'Available to trade'}</div></div>
    <button data-invite="${person.id}" ${person.busy ? 'disabled' : ''}>Invite</button>
  </div>`).join('') : '<p class="muted">No other penguins have accounts yet.</p>'
  const heading = selected ? `Trade with ${selected.nickname}` : 'Choose a penguin'
  const missing = requestedTarget && !selected
    ? `<div class="error">${escapeHtml(requestedName || 'That penguin')} is not available to trade.</div>` : ''
  root.innerHTML = chrome('Penguin Trading Post', `${player.nickname} · ${player.coins.toLocaleString()} coins`,
    `${missing}<h2>${escapeHtml(heading)}</h2><p class="muted">Send an invitation. They can accept when they open their Trading Post.</p><div class="player-list">${rows}</div>`,
    '<button class="ghost" id="logout">Sign out</button>')
  document.querySelector('#logout').onclick = () => logout()
  document.querySelectorAll('[data-invite]').forEach(button => button.onclick = () => invite(Number(button.dataset.invite)))
}

async function invite(targetId) {
  await action(() => api('/api/trades/invite', { method: 'POST', body: JSON.stringify({ target_id: targetId }) }))
}

function assetView(asset) {
  const visual = asset.kind === 'clothing'
    ? `<img src="${mediaOrigin}/avatar/paper/120/${asset.id}.png" alt="" onerror="this.style.visibility='hidden'">`
    : '<span class="icon">🛋️</span>'
  return `<div class="asset-chip">${visual}<span>${escapeHtml(asset.name)}${asset.quantity > 1 ? ` ×${asset.quantity}` : ''}</span></div>`
}

function offerPanel(person, other = false) {
  const ready = person.ready || person.confirmed
  return `<section class="offer-panel"><header class="offer-head ${other ? 'other' : ''}"><h2>${escapeHtml(person.nickname)}</h2></header>
    <div class="offer-body"><div class="coin-pill">🪙 ${person.coins.toLocaleString()} coins</div>
      <div class="asset-list">${person.assets.length ? person.assets.map(assetView).join('') : '<span class="muted">No items offered</span>'}</div></div>
    <div class="ready-stamp ${ready ? '' : 'waiting-stamp'}">${person.confirmed ? '✓ Confirmed' : ready ? '✓ Ready' : 'Waiting for Ready'}</div></section>`
}

function inventoryCard(item) {
  const key = `${item.kind}:${item.id}`
  const selected = model.draft.get(key) || 0
  const blocked = Boolean(item.blocked_reason)
  const visual = item.kind === 'clothing'
    ? `<img src="${mediaOrigin}/avatar/paper/120/${item.id}.png" alt="">`
    : '<span class="emoji">🛋️</span>'
  const quantity = item.kind === 'furniture' && !blocked
    ? `<span class="quantity"><button data-dec="${key}" ${selected <= 0 ? 'disabled' : ''}>−</button><b>${selected}</b><button data-inc="${key}" ${selected >= item.available ? 'disabled' : ''}>+</button></span>` : ''
  return `<div class="inventory-item ${selected ? 'selected' : ''} ${blocked ? 'blocked' : ''}" data-item="${key}" title="${escapeHtml(item.blocked_reason || '')}">
    ${visual}<span><strong>${escapeHtml(item.name)}</strong><small>${item.kind === 'furniture' ? `${item.available} available` : item.blocked_reason || 'Wearable'}</small></span>${quantity}</div>`
}

function syncDraft(trade) {
  const mine = trade.participants.find(person => person.is_me)
  if (!model.dirty && model.lastTradeId !== trade.id) {
    model.draft.clear()
    mine.assets.forEach(asset => model.draft.set(`${asset.kind}:${asset.id}`, asset.quantity))
    model.draftCoins = mine.coins
    model.lastTradeId = trade.id
  }
}

function renderTrade() {
  const trade = model.state.trade
  const mine = trade.participants.find(person => person.is_me)
  const other = trade.participants.find(person => !person.is_me)
  if (trade.status === 'invited' && mine.side === 1) {
    root.innerHTML = chrome('Trade invitation', `${model.state.player.nickname} · ${model.state.player.coins.toLocaleString()} coins`,
      `<div class="invitation"><div class="penguin">🐧</div><h2>${escapeHtml(other.nickname)} wants to trade</h2>
      <p class="muted">Review and edit both offers before anything can transfer.</p><div class="actions" style="justify-content:center">
      <button class="primary" id="accept">Accept invitation</button><button class="danger" id="cancel">Decline</button></div></div>`)
    document.querySelector('#accept').onclick = () => tradeAction('accept')
    document.querySelector('#cancel').onclick = () => tradeAction('cancel')
    return
  }
  if (trade.status === 'invited') {
    root.innerHTML = chrome('Invitation sent', `Waiting for ${other.nickname}`,
      `<div class="invitation"><div class="penguin">🐧 ··· 🐧</div><h2>Waiting for ${escapeHtml(other.nickname)}</h2>
      <p class="muted">They need to open their Trading Post and accept.</p><button class="danger" id="cancel">Cancel invitation</button></div>`)
    document.querySelector('#cancel').onclick = () => tradeAction('cancel')
    return
  }
  syncDraft(trade)
  const editable = trade.status === 'open' && !mine.ready
  const inventory = model.state.inventory[model.tab]
  root.innerHTML = chrome('Direct Trade', `Offer version ${trade.revision} · transfers only after both confirm`,
    `<div class="trade-grid">${offerPanel(mine)}<div class="trade-arrow">⇄</div>${offerPanel(other, true)}</div>
    ${trade.status === 'open' ? `<section class="editor">
      <div class="editor-top"><div><label for="coins">Coins to offer</label><input id="coins" type="number" min="0" max="${model.state.player.coins}" value="${model.draftCoins}" ${editable ? '' : 'disabled'}></div>
      <div class="muted">Available balance: ${model.state.player.coins.toLocaleString()} coins. Offered assets are reserved until this trade ends.</div></div>
      <div class="tabs"><button data-tab="clothing" class="${model.tab === 'clothing' ? 'active' : ''}">Wearables</button><button data-tab="furniture" class="${model.tab === 'furniture' ? 'active' : ''}">Furniture</button></div>
      <div class="inventory-grid">${inventory.length ? inventory.map(inventoryCard).join('') : '<p class="muted">No items in this category.</p>'}</div>
      <div class="actions" style="margin-top:14px"><button id="save-offer" ${editable ? '' : 'disabled'}>Update offer</button><span class="muted">Any update clears both Ready states.</span></div>
    </section>` : `<div class="invitation"><h2>Offers locked</h2><p class="muted">Check both sides carefully, then confirm.</p></div>`}
    <div class="trade-actions"><button class="danger" id="cancel">Cancel trade</button><div class="actions">
      ${trade.status === 'open' ? `<button class="primary" id="ready" ${mine.ready ? 'disabled' : ''}>${mine.ready ? 'Ready ✓' : 'Ready'}</button>` : ''}
      ${trade.status === 'locked' ? `<button class="confirm" id="confirm" ${mine.confirmed ? 'disabled' : ''}>${mine.confirmed ? 'Confirmed ✓' : 'Confirm Trade'}</button>` : ''}
    </div></div>`)
  document.querySelector('#cancel').onclick = () => tradeAction('cancel')
  document.querySelector('#ready')?.addEventListener('click', () => tradeAction('ready'))
  document.querySelector('#confirm')?.addEventListener('click', () => tradeAction('confirm'))
  document.querySelector('#save-offer')?.addEventListener('click', saveOffer)
  document.querySelector('#coins')?.addEventListener('input', event => { model.draftCoins = Number(event.target.value); model.dirty = true })
  document.querySelectorAll('[data-tab]').forEach(button => button.onclick = () => { model.tab = button.dataset.tab; renderTrade() })
  document.querySelectorAll('[data-item]').forEach(card => card.onclick = event => {
    if (!editable || card.classList.contains('blocked') || event.target.tagName === 'BUTTON') return
    const key = card.dataset.item
    if (key.startsWith('clothing:')) model.draft.set(key, model.draft.has(key) ? 0 : 1)
    model.dirty = true
    renderTrade()
  })
  document.querySelectorAll('[data-inc]').forEach(button => button.onclick = () => adjust(button.dataset.inc, 1))
  document.querySelectorAll('[data-dec]').forEach(button => button.onclick = () => adjust(button.dataset.dec, -1))
}

function adjust(key, delta) {
  model.draft.set(key, Math.max(0, (model.draft.get(key) || 0) + delta))
  model.dirty = true
  renderTrade()
}

async function saveOffer() {
  const assets = [...model.draft.entries()].filter(([, quantity]) => quantity > 0).map(([key, quantity]) => {
    const [kind, id] = key.split(':')
    return { kind, id: Number(id), quantity }
  })
  const result = await action(() => api(`/api/trades/${model.state.trade.id}/offer`, {
    method: 'PUT', body: JSON.stringify({ coins: model.draftCoins, assets })
  }))
  if (!result) return
  model.dirty = false
  toast('Offer updated. Both players must press Ready again.')
}

async function tradeAction(verb) {
  const result = await action(() => api(`/api/trades/${model.state.trade.id}/${verb}`, { method: 'POST' }))
  if (result?.trade?.status === 'complete') {
    const mine = result.trade.participants.find(person => person.is_me)
    const other = result.trade.participants.find(person => !person.is_me)
    toast(`Trade complete with ${other.nickname}: gave ${mine.coins} coins and ${mine.assets.length} item types.`)
  }
}

async function action(callback) {
  if (model.busy) return
  model.busy = true
  try {
    const result = await callback()
    await refresh(true)
    return result
  } catch (error) { toast(error.message) }
  finally { model.busy = false }
}

async function refresh(force = false) {
  if (!model.token || model.busy && !force) return
  try {
    const previous = model.state?.trade?.id
    model.state = await api('/api/state')
    const next = model.state.trade?.id
    if (previous && !next) { model.draft.clear(); model.dirty = false; model.lastTradeId = null }
    if (!model.dirty || previous !== next || force) render()
  } catch (error) {
    if (model.token) toast(error.message)
  }
}

function render() {
  if (!model.token) return renderLogin()
  if (!model.state) return
  model.state.trade ? renderTrade() : renderLobby()
}

render()
if (model.token) refresh(true)
setInterval(() => refresh(false), 1300)
