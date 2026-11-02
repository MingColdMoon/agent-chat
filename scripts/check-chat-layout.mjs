import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const rootDir = fileURLToPath(new URL('..', import.meta.url))
const edgePath =
  process.env.EDGE_PATH ||
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const port = Number(process.env.CDP_PORT || 9446)
const appUrl = process.env.APP_URL || 'http://127.0.0.1:18080'
const username = process.env.LAYOUT_USER || 'layout_test'
const password = process.env.LAYOUT_PASSWORD || 'AgentChat123!'
const viewportWidth = Number(process.env.LAYOUT_WIDTH || 1546)
const viewportHeight = Number(process.env.LAYOUT_HEIGHT || 937)

const edge = spawn(
  edgePath,
  [
    '--headless=new',
    '--no-sandbox',
    '--disable-gpu',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${rootDir}/.edge-layout-profile`,
    'about:blank',
  ],
  { stdio: 'ignore' },
)

async function waitForPage() {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const pages = await (
        await fetch(`http://127.0.0.1:${port}/json/list`)
      ).json()
      const page = pages.find((item) => item.type === 'page')
      if (page) return page
    } catch {
      // Browser is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 150))
  }
  throw new Error('Could not connect to Edge DevTools')
}

const page = await waitForPage()
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
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text)
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

await send('Page.enable')
await send('Runtime.enable')
await send('Network.enable')
await send('Network.setCacheDisabled', { cacheDisabled: true })
await send('Emulation.setDeviceMetricsOverride', {
  width: viewportWidth,
  height: viewportHeight,
  deviceScaleFactor: 1,
  mobile: viewportWidth < 600,
})

const loaded = once('Page.loadEventFired')
const cacheBustedUrl = `${appUrl}${appUrl.includes('?') ? '&' : '?'}v=${Date.now()}`
await send('Page.navigate', { url: cacheBustedUrl })
await loaded
await waitFor("document.querySelector('.auth-form') || document.querySelector('.app-shell')")

if (await evaluate("Boolean(document.querySelector('.auth-form'))")) {
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
      document.querySelector('.auth-form').requestSubmit();
    })()
  `)
  await waitFor("document.querySelector('.app-shell')")
}

await waitFor("document.querySelectorAll('.message').length > 0")
await new Promise((resolve) => setTimeout(resolve, 300))

const metrics = await evaluate(`
  (() => {
    const shell = document.querySelector('.app-shell');
    const main = document.querySelector('.main-panel');
    const scroller = document.querySelector('.message-scroller');
    const composer = document.querySelector('.composer-area');
    const initial = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollHeight;
    const maxScrollTop = scroller.scrollTop;
    scroller.scrollTop = 0;
    const minScrollTop = scroller.scrollTop;
    return {
      innerWidth,
      innerHeight,
      documentScrollHeight: document.documentElement.scrollHeight,
      shell: shell.getBoundingClientRect().toJSON(),
      main: main.getBoundingClientRect().toJSON(),
      scroller: scroller.getBoundingClientRect().toJSON(),
      scrollerClientHeight: scroller.clientHeight,
      scrollerScrollHeight: scroller.scrollHeight,
      initialScrollTop: initial,
      maxScrollTop,
      minScrollTop,
      canScroll: scroller.scrollHeight > scroller.clientHeight,
      composer: composer.getBoundingClientRect().toJSON(),
      composerVisible:
        composer.getBoundingClientRect().top < innerHeight &&
        composer.getBoundingClientRect().bottom <= innerHeight + 1
    };
  })()
`)

console.log(JSON.stringify(metrics, null, 2))
socket.close()
edge.kill()

