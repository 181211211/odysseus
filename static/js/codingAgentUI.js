// Visible Coding Agent lifecycle card for the existing Odysseus chat UI.
// Keeps model reasoning hidden; only task status and understandable tool activity
// supplied by the trusted backend lifecycle bridge are rendered.

const STATUS_LABELS = Object.freeze({
  planning: 'Planning',
  inspecting: 'Inspecting repository',
  editing: 'Editing files',
  testing: 'Running tests',
  fixing: 'Fixing errors',
  reviewing: 'Reviewing changes',
  waiting_approval: 'Waiting for approval',
  paused: 'Paused',
  failed: 'Failed',
  completed: 'Completed',
});

const TERMINAL = new Set(['completed', 'failed', 'paused', 'waiting_approval']);
const MAX_ACTIVITY = 8;

export function statusLabel(status) {
  const value = String(status || 'planning').toLowerCase();
  return STATUS_LABELS[value] || value.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
}

function short(value, limit = 160) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  return text.length > limit ? text.slice(0, limit - 1) + '…' : text;
}

export function activityLabel(data = {}) {
  const tool = String(data.tool || '');
  const path = short(data.path, 140);
  const command = short(data.command, 160);

  if (tool === 'coding_inspect') return 'Inspecting repository';
  if (tool === 'coding_git') return 'Reviewing Git changes';
  if (tool === 'read_file') return path ? `Reading ${path}` : 'Reading a file';
  if (tool === 'grep' || tool === 'glob' || tool === 'ls') return path ? `Searching ${path}` : 'Searching repository';
  if (tool === 'edit_file' || tool === 'apply_patch') return path ? `Editing ${path}` : 'Editing files';
  if (tool === 'write_file') return path ? `Writing ${path}` : 'Writing a file';
  if (tool === 'bash' || tool === 'python') return command ? `Running ${command}` : 'Running a development command';
  if (tool === 'coding_task') return 'Preparing coding task';
  return statusLabel(data.status);
}

function ensureStyles() {
  if (document.getElementById('coding-agent-ui-styles')) return;
  const style = document.createElement('style');
  style.id = 'coding-agent-ui-styles';
  style.textContent = `
    .coding-agent-card{max-width:760px;margin:10px 0 14px;padding:13px 15px;border:1px solid color-mix(in srgb,var(--accent,#7c6cff) 28%,transparent);border-radius:14px;background:color-mix(in srgb,var(--bg-secondary,#181818) 92%,var(--accent,#7c6cff) 8%);box-shadow:0 4px 18px rgba(0,0,0,.08);font-size:13px;color:var(--text-primary,#eee)}
    .coding-agent-head{display:flex;align-items:center;gap:10px;min-width:0}.coding-agent-title{font-weight:650;letter-spacing:.01em}.coding-agent-status{margin-left:auto;font-size:12px;opacity:.86;white-space:nowrap}.coding-agent-dot{width:9px;height:9px;border-radius:50%;background:var(--accent,#7c6cff);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent,#7c6cff) 16%,transparent);flex:0 0 auto}.coding-agent-card[data-terminal="false"] .coding-agent-dot{animation:codingAgentPulse 1.6s ease-in-out infinite}.coding-agent-card[data-status="completed"] .coding-agent-dot{background:#36b37e}.coding-agent-card[data-status="failed"] .coding-agent-dot{background:#ef5350}.coding-agent-card[data-status="waiting_approval"] .coding-agent-dot{background:#f5a623}.coding-agent-card[data-status="paused"] .coding-agent-dot{background:#8b8b8b}
    .coding-agent-task{margin-top:9px;opacity:.92;line-height:1.4;overflow-wrap:anywhere}.coding-agent-meta{display:flex;gap:12px;margin-top:8px;font-size:11px;opacity:.62}.coding-agent-activity{margin:10px 0 0;padding:9px 0 0;border-top:1px solid color-mix(in srgb,currentColor 12%,transparent);list-style:none}.coding-agent-activity li{display:flex;gap:8px;align-items:flex-start;padding:3px 0;opacity:.78;overflow-wrap:anywhere}.coding-agent-activity li::before{content:'›';opacity:.55}.coding-agent-activity li:last-child{opacity:1}
    @keyframes codingAgentPulse{0%,100%{opacity:.55;transform:scale(.9)}50%{opacity:1;transform:scale(1.08)}}
    @media (prefers-reduced-motion:reduce){.coding-agent-card .coding-agent-dot{animation:none!important}}
  `;
  document.head.appendChild(style);
}

function cardId(taskId) {
  return 'coding-agent-card-' + String(taskId || 'active').replace(/[^A-Za-z0-9_.-]/g, '_').slice(0, 100);
}

function createCard(data) {
  const box = document.getElementById('chat-history');
  if (!box) return null;
  ensureStyles();

  const card = document.createElement('section');
  card.id = cardId(data.task_id);
  card.className = 'coding-agent-card';
  card.setAttribute('role', 'status');
  card.setAttribute('aria-live', 'polite');

  const head = document.createElement('div');
  head.className = 'coding-agent-head';
  const dot = document.createElement('span');
  dot.className = 'coding-agent-dot';
  dot.setAttribute('aria-hidden', 'true');
  const title = document.createElement('span');
  title.className = 'coding-agent-title';
  title.textContent = 'Coding Agent';
  const status = document.createElement('span');
  status.className = 'coding-agent-status';
  head.append(dot, title, status);

  const task = document.createElement('div');
  task.className = 'coding-agent-task';
  task.hidden = true;
  const meta = document.createElement('div');
  meta.className = 'coding-agent-meta';
  const activity = document.createElement('ul');
  activity.className = 'coding-agent-activity';

  card.append(head, task, meta, activity);
  box.appendChild(card);
  return card;
}

export function handleStatus(data = {}) {
  let card = document.getElementById(cardId(data.task_id));
  if (!card) card = createCard(data);
  if (!card) return;

  const status = String(data.status || 'planning').toLowerCase();
  card.dataset.status = status;
  card.dataset.terminal = String(TERMINAL.has(status));
  const statusNode = card.querySelector('.coding-agent-status');
  if (statusNode) statusNode.textContent = statusLabel(status);

  const taskNode = card.querySelector('.coding-agent-task');
  if (taskNode && data.task) {
    taskNode.textContent = short(data.task, 320);
    taskNode.hidden = false;
  }

  const meta = card.querySelector('.coding-agent-meta');
  if (meta) {
    meta.textContent = '';
    const tools = document.createElement('span');
    tools.textContent = `${Number(data.tool_calls || 0)} tool call${Number(data.tool_calls || 0) === 1 ? '' : 's'}`;
    const iterations = document.createElement('span');
    iterations.textContent = `${Number(data.iterations || 0)} iteration${Number(data.iterations || 0) === 1 ? '' : 's'}`;
    meta.append(tools, iterations);
  }

  const list = card.querySelector('.coding-agent-activity');
  if (list) {
    const label = activityLabel(data);
    const last = list.lastElementChild;
    if (!last || last.textContent !== label) {
      const item = document.createElement('li');
      item.textContent = label;
      list.appendChild(item);
      while (list.children.length > MAX_ACTIVITY) list.firstElementChild.remove();
    }
  }

  if (card.scrollIntoView && !TERMINAL.has(status)) {
    card.scrollIntoView({ block: 'nearest' });
  }
}

export default { handleStatus, statusLabel, activityLabel };
