/**
 * Resource Hub 书签桥 —— Manifest V3 service worker（Chrome / Edge 通用）
 *
 * 职责：
 *   1. 发现本机 Resource Hub 的 HTTP 桥接端口（127.0.0.1:47821..47830）并记住；
 *   2. 每 1500ms 拉取一次删除命令（GET /commands），用 chrome.bookmarks API
 *      执行后回执（POST /ack）；
 *   3. 监听浏览器书签的删除/改名，批量上报（POST /events），失败时缓存重发。
 *
 * 设计约束：
 *   - 只用原生 JS，无第三方依赖；
 *   - 不产生未处理的 Promise 拒绝，任何异常都在内部吞掉；
 *   - 本机程序未启动（离线）时只在控制台警告一次，不刷屏。
 *
 * 协议（必须与后端 contract 完全一致）：
 *   GET  /ping      -> {"app":"resource-hub","protocol":1}
 *   GET  /commands  -> {"commands":[{"id":str,"op":"remove","urls":[str,...],"createdAt":str}]}
 *   POST /ack       <- {"results":[{"id":str,"removed":int,"failed":int}]}
 *   POST /events    <- {"events":[{"type":"removed","url":str,"title":str?},
 *                                 {"type":"changed","url":str,"title":str}]}
 */

'use strict';

// ---------------------------------------------------------------------------
// 协议常量
// ---------------------------------------------------------------------------
const APP_ID = 'resource-hub';
const PROTOCOL_VERSION = 1;
const HOST = '127.0.0.1';
const PORT_MIN = 47821;
const PORT_MAX = 47830;
const POLL_INTERVAL_MS = 1500;   // GET /commands 轮询间隔
const PING_TIMEOUT_MS = 400;     // 单端口 /ping 探测超时（顺序探测，必须短）
const REQUEST_TIMEOUT_MS = 2500; // /commands、/ack、/events 单次请求超时
const EVENT_BATCH_MS = 400;      // 浏览器书签事件的批量上报窗口
const MAX_PENDING_EVENTS = 500;  // 离线时未上报事件缓存上限
const MAX_EVENTS_PER_POST = 200; // 单次 POST /events 最多携带的事件条数

// ---------------------------------------------------------------------------
// 运行状态（service worker 被回收后重新加载时，关键状态会从 storage 恢复）
// ---------------------------------------------------------------------------
const runtime = {
  port: null,
  connected: false,
  offlineLogged: false,
  pendingEvents: [],
  flushTimer: null,
  flushing: false,
  started: false,
  initPromise: null,
};

// ---------------------------------------------------------------------------
// 小工具
// ---------------------------------------------------------------------------
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function ignoreError() {
  // 用于兜底吞掉 Promise 拒绝，避免 "Unhandled promise rejection"
}

function baseUrl(port) {
  return `http://${HOST}:${port}`;
}

function storageGet(keys) {
  try {
    return Promise.resolve(chrome.storage.local.get(keys)).catch(ignoreError);
  } catch (error) {
    return Promise.resolve({});
  }
}

function storageSet(items) {
  try {
    const pending = chrome.storage.local.set(items);
    if (pending && typeof pending.catch === 'function') {
      pending.catch(ignoreError);
    }
  } catch (error) {
    // storage 不可用时静默降级（不会影响同步主流程）
  }
}

/**
 * 发起一次 HTTP 请求，永不抛异常。
 * @returns {Promise<{ok: boolean, status: number, text: string}>}
 */
async function httpRequest(url, options, timeoutMs) {
  const hasAbortController = typeof AbortController === 'function';
  const controller = hasAbortController ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const init = {
      cache: 'no-store',
      credentials: 'omit',
      ...(options || {}),
    };
    if (controller) {
      init.signal = controller.signal;
    }
    const response = await fetch(url, init);
    let text = '';
    try {
      text = await response.text();
    } catch (error) {
      text = '';
    }
    return { ok: !!response.ok, status: response.status, text };
  } catch (error) {
    // 端口未监听 / 程序未启动 / 超时：这里只返回失败，不打印、不抛出
    return { ok: false, status: 0, text: '' };
  } finally {
    if (timer !== null) {
      clearTimeout(timer);
    }
  }
}

/**
 * GET 一个返回 JSON 的端点；失败或响应不是 JSON 时返回 null。
 */
async function fetchJson(url, timeoutMs) {
  const response = await httpRequest(url, {}, timeoutMs);
  if (!response.ok || !response.text) {
    return null;
  }
  try {
    return JSON.parse(response.text);
  } catch (error) {
    return null;
  }
}

/**
 * POST JSON；HTTP 2xx 即视为成功（后端可能返回任意/空响应体）。
 */
async function postJson(path, payload, timeoutMs) {
  if (runtime.port === null) {
    return false;
  }
  const response = await httpRequest(
    `${baseUrl(runtime.port)}${path}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    timeoutMs || REQUEST_TIMEOUT_MS,
  );
  return response.ok;
}

// ---------------------------------------------------------------------------
// 端口发现
// ---------------------------------------------------------------------------
/**
 * 顺序探测 47821..47830 的 GET /ping，命中 app=resource-hub 且 protocol=1 的端口。
 * 成功时记住端口（内存 + chrome.storage.local 的 "port" 键），失败返回 null。
 */
async function discoverPort() {
  for (let port = PORT_MIN; port <= PORT_MAX; port += 1) {
    const payload = await fetchJson(`${baseUrl(port)}/ping`, PING_TIMEOUT_MS);
    if (payload && payload.app === APP_ID && payload.protocol === PROTOCOL_VERSION) {
      runtime.port = port;
      storageSet({ port });
      return port;
    }
  }
  runtime.port = null;
  return null;
}

// ---------------------------------------------------------------------------
// 状态日志（离线只提示一次，避免刷屏）
// ---------------------------------------------------------------------------
function markOnline(port) {
  runtime.offlineLogged = false;
  if (!runtime.connected) {
    runtime.connected = true;
    console.log(`[Resource Hub] 已连接本机程序 127.0.0.1:${port}`);
  }
}

function markOffline() {
  runtime.connected = false;
  if (!runtime.offlineLogged) {
    runtime.offlineLogged = true;
    console.warn('[Resource Hub] 未连接本机程序，等待 bridge 端口 47821-47830 …');
  }
}

// ---------------------------------------------------------------------------
// 命令处理：GET /commands -> chrome.bookmarks 删除 -> POST /ack
// ---------------------------------------------------------------------------
/**
 * 用 chrome.bookmarks.search 精确查找某个 URL 的书签节点。
 * 先按 {url} 精确匹配；若没有结果，再用字符串 query 兜底（仍要求 node.url 全等）。
 */
async function findBookmarksByUrl(url) {
  const matches = [];
  const seen = new Set();
  const collect = (nodes) => {
    for (const node of nodes || []) {
      if (!node || node.url !== url || seen.has(node.id)) {
        continue;
      }
      seen.add(node.id);
      matches.push(node);
    }
  };
  try {
    collect(await chrome.bookmarks.search({ url }));
  } catch (error) {
    // 搜索失败按无结果处理
  }
  if (matches.length === 0) {
    try {
      collect(await chrome.bookmarks.search(url));
    } catch (error) {
      // ignore
    }
  }
  return matches;
}

/**
 * 执行后端下发的命令并回执。命令结构：{"id","op":"remove","urls":[...],"createdAt"}
 */
async function processCommands(commands) {
  if (!Array.isArray(commands) || commands.length === 0) {
    return;
  }
  const results = [];
  for (const command of commands) {
    if (!command || typeof command.id !== 'string' || !command.id) {
      continue;
    }
    if (command.op !== 'remove' || !Array.isArray(command.urls)) {
      continue;
    }
    let removed = 0;
    let failed = 0;
    for (const url of command.urls) {
      if (typeof url !== 'string' || url === '') {
        failed += 1;
        continue;
      }
      const nodes = await findBookmarksByUrl(url);
      // 浏览器中已不存在该 URL：无需操作，也不算失败（幂等）。
      for (const node of nodes) {
        try {
          await chrome.bookmarks.remove(node.id);
          removed += 1;
        } catch (error) {
          failed += 1;
        }
      }
    }
    results.push({ id: command.id, removed, failed });
  }
  if (results.length > 0) {
    // 回执失败不重试：后端会把未确认的命令重新下发，下一轮会再次幂等执行。
    await postJson('/ack', { results }, REQUEST_TIMEOUT_MS);
  }
}

// ---------------------------------------------------------------------------
// 反向事件：浏览器书签删除 / 改名 -> 批量 POST /events
// ---------------------------------------------------------------------------
function isSyncableUrl(url) {
  if (typeof url !== 'string' || url === '') {
    return false;
  }
  const lower = url.toLowerCase();
  if (lower.startsWith('chrome://') || lower.startsWith('edge://') || lower.startsWith('javascript:')) {
    return false;
  }
  return true;
}

function persistPendingEvents() {
  storageSet({ pendingEvents: runtime.pendingEvents.slice(-MAX_PENDING_EVENTS) });
}

function scheduleEventFlush() {
  if (runtime.flushTimer !== null) {
    return;
  }
  runtime.flushTimer = setTimeout(() => {
    runtime.flushTimer = null;
    // flushEvents 内部已保证不抛异常，这里再兜底一次。
    flushEvents().catch(ignoreError);
  }, EVENT_BATCH_MS);
}

function pushEvent(event) {
  if (!event || !isSyncableUrl(event.url)) {
    return;
  }
  runtime.pendingEvents.push(event);
  if (runtime.pendingEvents.length > MAX_PENDING_EVENTS) {
    runtime.pendingEvents = runtime.pendingEvents.slice(-MAX_PENDING_EVENTS);
  }
  persistPendingEvents();
  scheduleEventFlush();
}

/**
 * 把缓存的事件批量发给后端；失败则保留缓存，等连接恢复后由轮询再次触发。
 */
async function flushEvents() {
  if (runtime.flushing || runtime.pendingEvents.length === 0 || runtime.port === null) {
    return;
  }
  runtime.flushing = true;
  try {
    const batch = runtime.pendingEvents.slice(0, MAX_EVENTS_PER_POST);
    const ok = await postJson('/events', { events: batch }, REQUEST_TIMEOUT_MS);
    if (!ok) {
      persistPendingEvents();
      return;
    }
    runtime.pendingEvents.splice(0, batch.length);
    persistPendingEvents();
    if (runtime.pendingEvents.length > 0) {
      scheduleEventFlush();
    }
  } finally {
    runtime.flushing = false;
  }
}

// 书签被删除：只处理 URL 节点（文件夹没有 url，直接忽略）。
// 即便是本扩展按命令删除的节点也照常上报：后端是幂等的，并用它来裁剪 seen 账本。
chrome.bookmarks.onRemoved.addListener((id, removeInfo) => {
  try {
    const node = removeInfo && removeInfo.node;
    if (!node || typeof node.url !== 'string' || !isSyncableUrl(node.url)) {
      return;
    }
    pushEvent({
      type: 'removed',
      url: node.url,
      title: typeof node.title === 'string' ? node.title : '',
    });
  } catch (error) {
    // 监听器内绝不抛出
  }
});

// 书签被改名：changeInfo 只有 title 时才算改名（URL 变更不在本协议内）。
chrome.bookmarks.onChanged.addListener((id, changeInfo) => {
  try {
    if (!changeInfo || typeof changeInfo.title !== 'string') {
      return;
    }
    reportChangedTitle(id, changeInfo.title).catch(ignoreError);
  } catch (error) {
    // ignore
  }
});

async function reportChangedTitle(id, title) {
  let url = '';
  try {
    const nodes = await chrome.bookmarks.get(id);
    const node = Array.isArray(nodes) && nodes.length > 0 ? nodes[0] : null;
    if (node && typeof node.url === 'string') {
      url = node.url;
    }
  } catch (error) {
    return; // 节点可能已被删除
  }
  if (!isSyncableUrl(url)) {
    return;
  }
  pushEvent({ type: 'changed', url, title });
}

// ---------------------------------------------------------------------------
// 轮询主循环
// ---------------------------------------------------------------------------
/**
 * 保持 service worker 存活：MV3 的 worker 空闲约 30s 会被回收，
 * 每次轮询调用一个轻量扩展 API，使其空闲计时器重置（书签事件到来时也会被唤醒）。
 */
function keepAlive() {
  try {
    const pending = chrome.runtime.getPlatformInfo();
    if (pending && typeof pending.catch === 'function') {
      pending.catch(ignoreError);
    }
  } catch (error) {
    // ignore
  }
}

async function pollOnce() {
  keepAlive();

  let port = runtime.port;
  if (port === null) {
    port = await discoverPort();
    if (port === null) {
      markOffline();
      return;
    }
  }

  const payload = await fetchJson(`${baseUrl(port)}/commands`, REQUEST_TIMEOUT_MS);
  if (!payload || !Array.isArray(payload.commands)) {
    // 端口失效（程序退出或换了端口）：下一拍重新发现，不打印错误。
    runtime.port = null;
    markOffline();
    return;
  }

  markOnline(port);
  await processCommands(payload.commands);
  // 连接恢复时，顺便重发离线期间积压的事件。
  await flushEvents();
}

async function pollLoop() {
  for (;;) {
    try {
      await pollOnce();
    } catch (error) {
      // 任何异常都不能冒泡，否则会变成未处理的 Promise 拒绝。
    }
    await sleep(POLL_INTERVAL_MS);
  }
}

// ---------------------------------------------------------------------------
// 启动
// ---------------------------------------------------------------------------
async function init() {
  if (runtime.initPromise) {
    return runtime.initPromise;
  }
  runtime.initPromise = (async () => {
    const stored = (await storageGet(['port', 'pendingEvents'])) || {};
    if (Number.isInteger(stored.port) && stored.port >= PORT_MIN && stored.port <= PORT_MAX) {
      runtime.port = stored.port;
    }
    if (Array.isArray(stored.pendingEvents)) {
      const restored = stored.pendingEvents.filter((event) => event && isSyncableUrl(event.url));
      if (restored.length > 0) {
        runtime.pendingEvents = restored.concat(runtime.pendingEvents).slice(-MAX_PENDING_EVENTS);
      }
    }
  })();
  return runtime.initPromise;
}

function start() {
  if (runtime.started) {
    return;
  }
  runtime.started = true;
  init()
    .then(() => {
      if (runtime.pendingEvents.length > 0) {
        scheduleEventFlush();
      }
      return pollLoop();
    })
    .catch(() => {
      runtime.started = false;
    });
}

chrome.runtime.onInstalled.addListener(() => start());
chrome.runtime.onStartup.addListener(() => start());
try {
  // 点击扩展图标时唤醒 worker 并（重新）启动轮询（本扩展没有 popup）。
  chrome.action.onClicked.addListener(() => start());
} catch (error) {
  // 极老版本浏览器没有 action API 时忽略
}

start();
