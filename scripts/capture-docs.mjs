import { spawn } from 'node:child_process'
import { mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = fileURLToPath(new URL('..', import.meta.url))
const outputDir = join(rootDir, 'docs', 'images')
const edgePath =
  process.env.EDGE_PATH ||
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const port = Number(process.env.CDP_PORT || 9445)
const appUrl = process.env.APP_URL || 'http://127.0.0.1:18080'
const username = process.env.DOC_USERNAME || 'demo_alice'
const password = process.env.DOC_PASSWORD || 'AgentChat123!'
const profileDir =
  process.env.DOC_PROFILE || join(rootDir, '.edge-docs-profile')

await mkdir(outputDir, { recursive: true })

const edge = spawn(
  edgePath,
  [
    '--headless=new',
    '--no-sandbox',
    '--disable-gpu',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    'about:blank',
  ],
  { stdio: 'ignore' },
)

async function waitForJsonList() {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/list`)
      const pages = await response.json()
      const page = pages.find((item) => item.type === 'page')
      if (page) return page
    } catch {
      // Browser is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 150))
  }
  throw new Error('Could not connect to Edge DevTools')
}

const page = await waitForJsonList()
const socket = new WebSocket(page.webSocketDebuggerUrl)
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true })
  socket.addEventListener('error', reject, { once: true })
})

let nextId = 0
const pending = new Map()
const listeners = new Map()

socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data)
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id)
    pending.delete(message.id)
    if (message.error) reject(new Error(message.error.message))
    else resolve(message.result)
    return
  }
  for (const listener of listeners.get(message.method) || []) {
    listener(message.params)
  }
})

function send(method, params = {}) {
  const id = ++nextId
  socket.send(JSON.stringify({ id, method, params }))
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject })
  })
}

function once(method) {
  return new Promise((resolve) => {
    const handler = (params) => {
      listeners.set(
        method,
        (listeners.get(method) || []).filter((item) => item !== handler),
      )
      resolve(params)
    }
    listeners.set(method, [...(listeners.get(method) || []), handler])
  })
}

async function evaluate(expression) {
  const result = await send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  })
  if (result.exceptionDetails) {
    throw new Error(
      result.exceptionDetails.exception?.description ||
        result.exceptionDetails.text,
    )
  }
  return result.result.value
}

async function waitFor(expression, timeoutMs = 15_000) {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    if (await evaluate(`Boolean(${expression})`)) return
    await new Promise((resolve) => setTimeout(resolve, 150))
  }
  throw new Error(`Timed out waiting for ${expression}`)
}

async function capture(name) {
  const screenshot = await send('Page.captureScreenshot', {
    format: 'png',
    fromSurface: true,
    captureBeyondViewport: false,
  })
  await writeFile(
    join(outputDir, name),
    Buffer.from(screenshot.data, 'base64'),
  )
}

async function setViewport(width, height) {
  await send('Emulation.setDeviceMetricsOverride', {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width < 600,
  })
}

async function navigate() {
  const loaded = once('Page.loadEventFired')
  await send('Page.navigate', { url: appUrl })
  await loaded
  await evaluate('document.fonts.ready')
  await new Promise((resolve) => setTimeout(resolve, 300))
}

await send('Page.enable')
await send('Runtime.enable')

await setViewport(1440, 900)
await navigate()
await waitFor("document.querySelector('.auth-form')")
await capture('login-desktop.png')

await setViewport(390, 844)
await navigate()
await waitFor("document.querySelector('.auth-form')")
await capture('login-mobile.png')

await setViewport(1440, 900)
await navigate()
await waitFor("document.querySelector('.auth-form')")

async function fillCredentials() {
  await evaluate(`
    (() => {
      const setValue = (input, value) => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLInputElement.prototype,
          'value'
        ).set;
        setter.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      };
      const inputs = document.querySelectorAll('.auth-input input');
      setValue(inputs[0], ${JSON.stringify(username)});
      setValue(inputs[1], ${JSON.stringify(password)});
    })()
  `)
}

await evaluate(`
  [...document.querySelectorAll('.auth-tabs button')]
    .find((button) => button.textContent.trim() === '注册')
    .click()
`)
await fillCredentials()
await evaluate("document.querySelector('.auth-form').requestSubmit()")

try {
  await waitFor("document.querySelector('.app-shell')", 4_000)
} catch {
  await evaluate(`
    [...document.querySelectorAll('.auth-tabs button')]
      .find((button) => button.textContent.trim() === '登录')
      .click()
  `)
  await fillCredentials()
  await evaluate("document.querySelector('.auth-form').requestSubmit()")
  await waitFor("document.querySelector('.app-shell')", 15_000)
}

await evaluate(`
  new Promise((resolve) => setTimeout(resolve, 500))
`)

if (!(await evaluate("document.querySelectorAll('.message').length > 0"))) {
  await evaluate(`
    (() => {
      const textarea = document.querySelector('.composer textarea');
      const setter = Object.getOwnPropertyDescriptor(
        HTMLTextAreaElement.prototype,
        'value'
      ).set;
      setter.call(textarea, '计算 (18 * 24) / 6');
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      document.querySelector('.composer').requestSubmit();
    })()
  `)
  try {
    await waitFor("document.querySelector('.leibox-dot-loader')", 2_500)
    await capture('agent-loading.png')
  } catch {
    // The demo can finish before a screenshot is useful.
  }
  await waitFor(
    "document.querySelector('.message.assistant .message-content')",
    20_000,
  )
  await waitFor(
    "document.querySelector('.composer-status')?.textContent.includes('就绪')",
    20_000,
  )
}

await capture('conversation.png')

await evaluate("document.querySelector('.marketplace-link').click()")
await waitFor("document.querySelector('.marketplace')")
await new Promise((resolve) => setTimeout(resolve, 300))
await capture('marketplace.png')

await evaluate(`
  (() => {
    const input = document.querySelector('.marketplace-search input');
    const setter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      'value'
    ).set;
    setter.call(input, 'MediaCrawler');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  })()
`)
await waitFor("document.querySelectorAll('.agent-card').length === 1")
await evaluate(`
  (() => {
    const input = document.querySelector('.marketplace-search input');
    const setter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      'value'
    ).set;
    setter.call(input, '');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  })()
`)
await waitFor("document.querySelectorAll('.agent-card').length > 1")

await evaluate("document.querySelector('.create-agent-button').click()")
await waitFor("document.querySelector('.agent-create-panel')")
await new Promise((resolve) => setTimeout(resolve, 450))
await capture('create-agent.png')

await evaluate(`
  document.querySelector('.agent-create-panel .settings-header .icon-button').click()
`)
await waitFor("!document.querySelector('.agent-create-panel')")
await evaluate(`
  (() => {
    const card = [...document.querySelectorAll('.agent-card')].find(
      (item) => item.querySelector('h3')?.textContent.trim() === '装机大师'
    );
    card.querySelector('.agent-primary-action').click();
  })()
`)
await waitFor("document.querySelector('.pc-configurator')")
await new Promise((resolve) => setTimeout(resolve, 300))
await capture('pc-builder-empty.png')

await evaluate(`
  (() => {
    const range = document.querySelector('.budget-control input');
    const setter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      'value'
    ).set;
    setter.call(range, '10000');
    range.dispatchEvent(new Event('input', { bubbles: true }));
    range.dispatchEvent(new Event('change', { bubbles: true }));
    document.querySelector('.pc-build-submit').click();
  })()
`)
await waitFor("document.querySelector('.pc-build-card')", 25_000)
await new Promise((resolve) => setTimeout(resolve, 300))
await evaluate(`
  (() => {
    const scroller = document.querySelector('.message-scroller');
    const card = document.querySelector('.pc-build-card');
    scroller.scrollTop +=
      card.getBoundingClientRect().top -
      scroller.getBoundingClientRect().top -
      88;
  })()
`)
await new Promise((resolve) => setTimeout(resolve, 150))
await capture('pc-builder-plan.png')

await evaluate("document.querySelector('.marketplace-link').click()")
await waitFor("document.querySelector('.marketplace')")
await waitFor(
  "[...document.querySelectorAll('.agent-card h3')].some((item) => item.textContent.includes('MediaCrawler'))",
)
await evaluate(`
  (() => {
    const card = [...document.querySelectorAll('.agent-card')].find(
      (item) =>
        item.querySelector('h3')?.textContent.includes('MediaCrawler')
    );
    if (!card) throw new Error('MediaCrawler agent card not found');
    card.querySelector('.agent-primary-action').click();
  })()
`)
await waitFor("document.querySelector('.crawler-configurator')")
await new Promise((resolve) => setTimeout(resolve, 300))
await capture('media-crawler-empty.png')

await evaluate(`
  (() => {
    const input = document.querySelector('.crawler-field input[type="text"]');
    const setter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      'value'
    ).set;
    setter.call(input, 'AI 效率工具');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  })()
`)
await new Promise((resolve) => setTimeout(resolve, 100))
await evaluate("document.querySelector('.crawler-submit').click()")
await waitFor("document.querySelector('.crawler-task-card')", 25_000)
await new Promise((resolve) => setTimeout(resolve, 300))
await evaluate(`
  (() => {
    const scroller = document.querySelector('.message-scroller');
    const card = document.querySelector('.crawler-task-card');
    scroller.scrollTop +=
      card.getBoundingClientRect().top -
      scroller.getBoundingClientRect().top -
      88;
  })()
`)
await new Promise((resolve) => setTimeout(resolve, 150))
await capture('media-crawler-task.png')

await setViewport(390, 844)
await navigate()
await waitFor("document.querySelector('.app-shell')")
await evaluate("document.querySelector('.mobile-menu').click()")
await waitFor("document.querySelector('.sidebar.open')")
await evaluate("document.querySelector('.marketplace-link').click()")
await waitFor("document.querySelector('.marketplace')")
await waitFor(
  "[...document.querySelectorAll('.agent-card h3')].some((item) => item.textContent.includes('MediaCrawler'))",
)
await evaluate(`
  (() => {
    const card = [...document.querySelectorAll('.agent-card')].find(
      (item) => item.querySelector('h3')?.textContent.includes('MediaCrawler')
    );
    card.querySelector('.agent-primary-action').click();
  })()
`)
await waitFor("document.querySelector('.crawler-configurator')")
await new Promise((resolve) => setTimeout(resolve, 300))
await capture('media-crawler-mobile.png')

await send('Emulation.clearDeviceMetricsOverride')
console.log(`Documentation screenshots written to ${outputDir}`)

socket.close()
edge.kill()

