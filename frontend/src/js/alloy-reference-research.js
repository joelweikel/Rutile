import {studioApi, studioPost} from './alloy-runs.js';

const endpoint = '/api/reference-research';
const labels = {density: 'Density', elasticity: 'Elasticity'};
const storage = 'rutile.reference-research.v1';
const defaults = {mode: 'after_idle', idle_minutes: 30};
const hostLabels = {codex: 'Codex', codex_custom: 'Custom Codex', pi: 'Pi'};
const settingsButton = '<button type="button" class="secondary" data-research-settings>Research agent settings</button>';

export function researchTargets(set) {
  return (set?.phases || []).flatMap(phase => {
    if (phase.phase === 'LIQUID' || phase.phase.startsWith('LIQUID#')) return [];
    const targets = [];
    if (phase.density_model?.state !== 'estimated' && !phase.reference?.density_g_cm3) {
      targets.push({phase_id: phase.instance_id, property: 'density', phase,
        temperature_k: set.temperature_k, pressure_pa: set.pressure_pa,
        reason: phase.density_model?.reason || phase.reason || 'No applicable density'});
    }
    if (!phase.elasticity) {
      targets.push({phase_id: phase.instance_id, property: 'elasticity', phase,
        temperature_k: set.temperature_k, pressure_pa: set.pressure_pa,
        reason: phase.elasticity_reason || phase.reason || 'No applicable elastic moduli'});
    }
    return targets;
  });
}

function readProject(project) {
  try { return JSON.parse(localStorage.getItem(storage))?.[project] || {}; }
  catch { return {}; }
}

function saveProject(project, value) {
  let saved;
  try { saved = JSON.parse(localStorage.getItem(storage)) || {}; } catch { saved = {}; }
  saved[project] = value;
  localStorage.setItem(storage, JSON.stringify(saved));
}

export function createReferenceResearch(dialog, {escape, format, apply, message}) {
  const body = dialog.querySelector('[data-research-body]');
  const notice = dialog.querySelector('[data-research-notice]');
  let anchor, saved, batch, interval, busy = false, generation = 0, hosts = [], connector = false;
  const requestPath = () => `${endpoint}/requests/${anchor.project_id}/${batch.request_id}`;
  const setNotice = value => { notice.textContent = value; };

  function configure(targets, selectedPhase) {
    const settings = {...defaults, ...saved.session};
    const initialHost = settings.delivery === 'manual' ? '' :
      hosts.includes(settings.host) ? settings.host : hosts[0] || '';
    body.innerHTML = `<form class="studio-research-form" data-research-form>
      <fieldset><legend>Missing properties</legend>
      ${targets.length ? `<p class="fine">${format(targets[0].temperature_k)} K · ${format(targets[0].pressure_pa)} Pa</p>` :
        '<p class="fine">All supported properties have data for this assignment.</p>'}
      ${targets.map((target, index) => `<label class="studio-research-option">
        <input type="checkbox" name="target" value="${index}" ${!selectedPhase || selectedPhase === target.phase_id ? 'checked' : ''}>
        <span><strong>${escape(target.phase.label)} · ${labels[target.property]}</strong>
        <small>${escape(target.reason)} · ${Object.entries(target.phase.composition).map(([e, x]) =>
          `${escape(e)} ${format(x * 100)} at%`).join(' · ')}</small></span></label>`).join('')}
      </fieldset><div class="studio-research-options">
      <label>Research agent<select name="host">
        ${hosts.map(host => `<option value="${host}" ${initialHost === host ? 'selected' : ''}>${hostLabels[host]}</option>`).join('')}
        <option value="" ${!initialHost ? 'selected' : ''}>Manual MCP handoff</option></select></label>
      <p class="fine" data-research-delivery></p>
      <div class="studio-research-options" data-auto-session>
      <label>Conversation<select name="mode">
      ${Object.entries({resume: 'Always resume', fresh: 'Always start fresh', after_idle: 'Start fresh after inactivity'}).map(([value, label]) =>
        `<option value="${value}" ${settings.mode === value ? 'selected' : ''}>${label}</option>`).join('')}
      </select></label>
      <label data-idle-field ${settings.mode === 'after_idle' ? '' : 'hidden'}>Idle time (minutes)
      <input type="number" name="idle_minutes" min="1" max="1440" value="${escape(settings.idle_minutes)}" required></label>
      </div>
      <p class="fine">The agent receives the selected phase compositions, structures, and conditions. Review its findings before applying any values.</p>
      </div>
      <div class="studio-research-actions">
      <button type="submit" class="primary" ${targets.length ? '' : 'disabled'}></button>
      <button type="button" class="secondary" data-research-recent>Browse research batches</button>
      ${settingsButton}
      </div>
      </form>`;
    const form = body.querySelector('form');
    function updateChoice() {
      const name = hostLabels[form.elements.host.value];
      const useIdleTime = name && form.elements.mode.value === 'after_idle';
      form.querySelector('[data-idle-field]').hidden = !useIdleTime;
      form.elements.idle_minutes.disabled = !useIdleTime;
      form.querySelector('[data-auto-session]').hidden = !name;
      form.querySelector('[data-research-delivery]').textContent = name ?
        `Rutile starts ${name}, sends the task, and shows its output here.` :
        'Rutile prepares a task for you to send in a chat with the Rutile MCP tools enabled.';
      form.querySelector('button[type="submit"]').textContent = name ?
        `Start ${name} research` : 'Prepare manual handoff';
    }
    updateChoice();
    form.addEventListener('change', updateChoice);
    form.addEventListener('submit', event => {
      event.preventDefault();
      const data = new FormData(form);
      const chosen = data.getAll('target').map(index => {
        const {phase_id, property} = targets[index];
        return {phase_id, property};
      });
      if (!chosen.length) { setNotice('Select at least one missing property.'); return; }
      void perform(async () => {
        const {targets: _, ...context} = anchor;
        const session = {mode: data.get('mode'), idle_minutes: Number(data.get('idle_minutes') ?? settings.idle_minutes)};
        const host = data.get('host');
        batch = await studioPost(`${endpoint}/requests`, {...context, targets: chosen, session, share_with_agent: true});
        saved = {...saved, session: {...session, host, delivery: host ? 'automatic' : 'manual'}};
        saveProject(anchor.project_id, saved);
        render();
        if (host) await studioPost(`${requestPath()}/launch`, {host});
        await refresh();
      });
    });
  }

  function taskText() {
    return `Research Rutile batch ${batch.request_id} for project ${anchor.project_id}. Use the Rutile MCP tool get_reference_request to read the approved targets, saved evidence and scratch directory. Read the returned AGENTS.md instructions. Follow host permissions for retrieval and isolated offline Python. Use stage_phase_data_proposal for each target you can support, or record what remains unresolved.`;
  }

  function updateActivity() {
    const {host, state} = batch;
    const activity = batch.activity || {};
    const active = state === 'collecting' && host?.running;
    const name = hostLabels[host?.name] || 'Agent';
    const terminal = {completed: 'Research finished', failed: 'Research needs attention', canceled: 'Research canceled'};
    const stateLabel = terminal[state] || (active ? (activity.phase === 'running' ? `${name} is running` : `Starting ${name}…`) :
      activity.mcp ? 'Manual handoff · MCP activity received' : 'Waiting for manual handoff');
    const status = body.querySelector('[data-research-state]');
    if (status.textContent !== stateLabel) status.textContent = stateLabel;
    status.dataset.active = active;
    const metrics = body.querySelector('[data-research-metrics]');
    const staged = new Set((batch.proposals || []).map(proposal => proposal.target_id)).size;
    const total = Object.keys(batch.targets).length;
    const seconds = activity.ended_elapsed_s || activity.usage_elapsed_s;
    const rate = Number.isFinite(activity.output_tokens) ?
      ` · ${activity.output_tokens.toLocaleString()} output tokens${seconds > 0 ?
        ` · ${(activity.output_tokens / seconds).toFixed(1)} avg output tok/s` : ''}` : '';
    const duration = active ? Date.now() / 1000 - activity.started_at : activity.ended_elapsed_s;
    const elapsed = Number.isFinite(duration) ? ` · ${Math.max(0, Math.floor(duration))} s elapsed` : '';
    metrics.textContent = `${staged}/${total} targets with findings${elapsed}${rate}`;
    const output = body.querySelector('[data-agent-output]');
    const text = activity.output || (active ? 'Waiting for the agent’s first message…' :
      host ? 'The launcher recorded no agent messages for this run.' :
      'For a manual handoff, read the agent’s replies in your chat. Rutile shows MCP activity and proposals here.');
    if (output.textContent !== text) {
      const atBottom = output.scrollHeight - output.clientHeight - output.scrollTop < 28;
      output.textContent = text;
      if (atBottom) output.scrollTop = output.scrollHeight;
    }
    const events = [...(activity.events || []), ...(activity.mcp ? [activity.mcp] : [])].sort((a, b) => b.at - a.at);
    body.querySelector('[data-agent-events]').innerHTML = events.slice(0, 8).map(event =>
      `<li><time>${escape(new Date(event.at * 1000).toLocaleTimeString())}</time> ${escape(event.label)}</li>`).join('') ||
      '<li>No activity received yet.</li>';
  }

  function render() {
    if (!dialog.open || !batch) return;
    const checked = new Set([...body.querySelectorAll('[data-proposal]:checked')].map(input => input.value));
    const previousSections = new Set([...body.querySelectorAll('[data-research-target]')].map(section => section.dataset.researchTarget));
    const focused = document.activeElement?.getAttribute('data-research-focus');
    const scroll = body.querySelector('[data-research-review]')?.scrollTop || 0;
    const proposals = batch.proposals || [];
    const current = batch.equilibrium_job === anchor.equilibrium_job;
    const active = batch.state === 'collecting' && batch.host?.running;
    const manual = batch.state === 'collecting' && !active;
    const launchHost = !active && batch.state !== 'completed' &&
      (hosts.includes(batch.host?.name) ? batch.host.name : hosts[0]);
    body.innerHTML = `<div class="studio-research-run">
      <div class="studio-research-status">
        <div><strong data-research-state role="status"></strong><p class="fine" data-research-metrics></p></div>
        <div class="studio-research-actions">
          ${launchHost ? `<button type="button" class="primary" data-research-launch="${launchHost}" data-research-focus="launch">
            ${batch.host ? 'Retry with' : 'Start'} ${hostLabels[launchHost]}${batch.host ? '' : ' research'}</button>` : ''}
          ${active || manual ?
            `<button type="button" class="secondary" data-research-stop data-research-focus="stop">${active ? 'Stop agent' : 'Close batch to agent'}</button>` : ''}
          ${manual && proposals.length ? '<button type="button" class="secondary" data-research-finish>Finish handoff</button>' : ''}
          <button type="button" class="secondary" data-research-new data-research-focus="new">New batch</button>
          <button type="button" class="secondary" data-research-recent data-research-focus="batches">Browse batches</button>
        </div>
      </div>
      ${batch.host?.error ? `<div class="studio-research-actions"><p class="fine studio-warning">${escape(batch.host.error)}</p>${settingsButton}</div>` : ''}
      ${current ? '' : '<p class="fine studio-warning">This batch refers to an earlier equilibrium calculation.</p>'}
      <div class="studio-research-columns">
      <section class="studio-research-monitor" aria-label="Agent monitor">
        ${manual ? `<div class="studio-research-handoff">
          <h3>Manual MCP handoff</h3>
          <ol class="fine">
            <li>${connector ? 'Open a chat with Rutile MCP enabled.' : 'Prepare and register the Rutile MCP in Research agent settings.'}</li>
            <li>Copy the task, paste it into that chat, and send it.</li>
            <li>Keep Rutile open. Findings appear here as the agent submits them.</li>
          </ol>
          <div class="studio-research-actions"><button type="button" class="secondary" data-research-copy
            data-research-focus="copy">Copy task for agent</button>${settingsButton}
            <button type="button" class="secondary" data-show-task aria-expanded="false">View task text</button></div>
          <textarea hidden readonly rows="3" aria-label="Research task" data-task-text>${escape(taskText())}</textarea>
        </div>` : ''}
        <h3>Agent output</h3>
        <pre tabindex="0" aria-label="Agent output" data-agent-output></pre>
        <h3>Recent activity</h3>
        <ul class="fine studio-research-events" data-agent-events></ul>
        ${batch.host?.decision ? `<p class="fine">${escape(batch.host.decision.reason)}</p>` : ''}
      </section>
      <section class="studio-research-review" data-research-review aria-label="Phase findings">
      <h3>Phase findings</h3>
      ${Object.entries(batch.targets).map(([key, target]) => {
        const candidates = proposals.filter(item => item.target_id === key);
        const selected = candidates.find(item => checked.has(item.proposal_id)) ||
          (!previousSections.has(key) || !body.querySelector(`[data-research-target="${key}"] [data-proposal]`) ?
            candidates.find(item => item.state === 'ready') : null);
        return `<section class="studio-research-target" data-research-target="${key}">
          <h4>${escape(target.label)} · ${labels[target.property]}</h4>
          <p class="fine">${escape(target.reason)}</p>
          ${candidates.length ? candidates.map(item => proposalMarkup(item, selected?.proposal_id === item.proposal_id, key)).join('') :
            '<p class="fine">Awaiting a finding</p>'}
        </section>`;
      }).join('')}
      </section></div>
      <div class="studio-research-actions">
        <button type="button" class="secondary" data-research-apply="only" data-research-focus="apply"
          ${!current || !proposals.some(p => p.state === 'ready') ? 'disabled' : ''}>Apply selected</button>
        <button type="button" class="primary" data-research-apply="run" data-research-focus="apply-run"
          ${!current || !proposals.some(p => p.state === 'ready') ? 'disabled' : ''}>Apply and rerun</button>
      </div></div>`;
    body.querySelector('[data-research-review]').scrollTop = scroll;
    updateActivity();
    if (focused) [...body.querySelectorAll('[data-research-focus]')].find(control =>
      control.dataset.researchFocus === focused)?.focus({preventScroll: true});
  }

  function proposalMarkup(item, checked, key) {
    const candidate = item.candidate;
    const sources = item.sources.map(source => `<li><a href="${escape(source.url)}" target="_blank"
      rel="noopener noreferrer">${escape(source.title)}</a> · ${escape(source.locator)}</li>`).join('');
    const artifacts = Object.entries(item.artifacts).map(([name, artifact]) => `<li><a
      href="${requestPath()}/artifacts/${item.proposal_id}/${artifact.sha256}" download>${escape(name)}</a></li>`).join('');
    const values = candidate ? Object.entries(candidate.values).map(([name, value]) =>
      `${escape(name.replaceAll('_', ' '))} ${format(value.value)} ${escape(value.unit)}`).join(' · ') : '';
    return `<article class="studio-research-proposal">
      ${item.state === 'ready' ? `<label class="studio-research-option"><input type="checkbox" name="${key}" value="${item.proposal_id}"
        data-proposal data-research-focus="${item.proposal_id}" ${checked ? 'checked' : ''}><strong>${values}</strong></label>` :
        `<p class="fine">${escape(item.reason)}</p>`}
      ${sources ? `<ul>${sources}</ul>` : ''}
      ${artifacts ? `<details><summary>Saved files</summary><ul>${artifacts}</ul></details>` : ''}
      ${candidate ? `<p class="fine">${escape(candidate.method === 'measured' ? 'Measured' :
        candidate.extrapolated ? 'Computed · extrapolated' : 'Computed')} · ${escape(candidate.derivation)}</p>
        ${candidate.applicability ? `<p class="fine">${escape(candidate.applicability)}</p>` : ''}
        ${candidate.uncertainty ? `<p class="fine">${escape(candidate.uncertainty)}</p>` : ''}
        <p class="fine">${format(candidate.temperature_k)} K · ${format(candidate.pressure_pa)} Pa ·
        ${Object.entries(candidate.composition_mole_fraction).map(([e, x]) => `${escape(e)} ${format(100*x)} at%`).join(' · ')}</p>` : ''}
      </article>`;
  }

  async function refresh() {
    if (!batch || !dialog.open) return;
    const version = generation;
    const path = requestPath();
    const updated = await studioApi(path);
    if (generation !== version || !batch || !dialog.open || path !== requestPath()) return;
    const {activity: previous, ...original} = batch;
    const {activity, ...structure} = updated;
    batch = updated;
    if (JSON.stringify(original) !== JSON.stringify(structure) || Boolean(previous?.mcp) !== Boolean(activity?.mcp)) render();
    else if (batch.host?.running || JSON.stringify(previous) !== JSON.stringify(activity)) updateActivity();
  }

  async function openHistory() {
    const result = await studioApi(`${endpoint}/requests/${anchor.project_id}?assignment_node=${encodeURIComponent(anchor.assignment_node)}`);
    batch = null;
    const labels = {collecting: 'Open batch', completed: 'Finished', failed: 'Needs attention', canceled: 'Canceled'};
    body.innerHTML = `<h3>Research batches</h3>
      ${result.batches.map(item => `<p><button type="button" class="secondary" data-research-batch="${escape(item.request_id)}">
        ${escape(new Date(item.created_at * 1000).toLocaleString())} · ${escape(labels[item.state] || item.state)}
      </button></p>`).join('') || '<p class="fine">No research batches for this phase assignment yet.</p>'}
      <button type="button" class="secondary" data-research-new>New batch</button>`;
  }

  async function perform(operation) {
    if (busy) return;
    busy = true;
    try { setNotice(''); await operation(); }
    catch (error) { setNotice(error.message); }
    finally { busy = false; }
  }

  dialog.addEventListener('close', () => {
    generation++;
    clearInterval(interval);
  });
  dialog.querySelector('[data-research-close]').addEventListener('click', () => dialog.close());
  body.addEventListener('change', event => {
    const input = event.target;
    if (input.matches('[data-proposal]') && input.checked) {
      for (const other of input.closest('[data-research-target]').querySelectorAll('[data-proposal]')) {
        if (other !== input) other.checked = false;
      }
    }
  });
  body.addEventListener('click', event => {
    const showTask = event.target.closest('[data-show-task]');
    if (showTask) {
      const task = body.querySelector('[data-task-text]');
      task.hidden = !task.hidden;
      showTask.setAttribute('aria-expanded', String(!task.hidden));
      if (!task.hidden) task.focus();
      return;
    }
    const button = event.target.closest('button');
    if (!button || button.type === 'submit') return;
    if (button.hasAttribute('data-research-settings')) {
      dialog.close();
      document.dispatchEvent(new Event('rutile:research-settings'));
      return;
    }
    void perform(async () => {
      if (button.hasAttribute('data-research-recent')) {
        await openHistory();
      } else if (button.dataset.researchBatch) {
        batch = await studioApi(`${endpoint}/requests/${anchor.project_id}/${button.dataset.researchBatch}`);
        render();
      } else if (button.hasAttribute('data-research-new')) {
        batch = null;
        configure(anchor.targets);
      } else if (button.hasAttribute('data-research-copy')) {
        try {
          await navigator.clipboard.writeText(taskText());
          setNotice('Task copied. Paste it into your chat with Rutile MCP enabled and send it.');
        } catch {
          const task = body.querySelector('[data-task-text]');
          task.hidden = false;
          task.select();
          setNotice('Copy the selected task text, then paste and send it in your MCP chat.');
        }
      } else if (button.hasAttribute('data-research-stop')) {
        await studioPost(`${requestPath()}/finish`, {state: 'canceled'});
        await refresh();
      } else if (button.hasAttribute('data-research-finish')) {
        await studioPost(`${requestPath()}/finish`, {state: 'completed'});
        await refresh();
      } else if (button.dataset.researchLaunch) {
        await studioPost(`${requestPath()}/launch`, {host: button.dataset.researchLaunch});
        await refresh();
      } else if (button.dataset.researchApply) {
        const proposals = [...body.querySelectorAll('[data-proposal]:checked')].map(control => control.value);
        if (!proposals.length) { setNotice('Select at least one applicable proposal.'); return; }
        const submit = () => studioPost(`${requestPath()}/review`, {proposals,
          project_id: anchor.project_id, assignment_node: anchor.assignment_node, equilibrium_job: anchor.equilibrium_job});
        await apply(anchor, submit, button.dataset.researchApply === 'run', () => dialog.close());
      }
    });
  });

  return async function open(context, selectedPhase, recent = false) {
    if (dialog.open || busy) return;
    anchor = context;
    saved = readProject(anchor.project_id);
    batch = null;
    body.textContent = '';
    setNotice('');
    const version = ++generation;
    dialog.showModal();
    try {
      const available = await studioApi(`${endpoint}/hosts`);
      if (version !== generation) return;
      hosts = available.hosts.filter(host => Object.hasOwn(hostLabels, host));
      connector = available.connector_configured;
      if (recent) await openHistory();
      else configure(anchor.targets, selectedPhase);
      if (version !== generation) return;
      interval = setInterval(() => {
        if (batch && !busy) void refresh().catch(error => setNotice(error.message));
      }, 900);
    } catch (error) {
      if (version === generation) setNotice(error.message);
      else message(error.message);
    }
  };
}
