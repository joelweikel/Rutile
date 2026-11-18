import {studioApi, studioPost} from './alloy-runs.js';

const endpoint = '/api/reference-research/setup';

export function initResearchSettings() {
  const panel = document.getElementById('research-agent-settings');
  const find = selector => panel.querySelector(selector);
  const codex = find('[data-save-agent]').elements.executable;
  const launcher = find('[data-custom-launcher]');
  const notice = find('[data-agent-status]');
  let setup, busy = false;

  function render() {
    codex.placeholder = setup.codex_executable || 'Detect automatically';
    find('[data-codex-status]').textContent = setup.codex_executable ?
      'Codex executable found. Rutile can launch it from Alloy Studio.' :
      'Codex executable unavailable. Install Codex or save its full path.';
    const [executable, ...args] = setup.bridge;
    find('[data-bridge-exe]').value = executable;
    find('[data-bridge-args]').value = JSON.stringify(args);
    find('[data-connector-status]').textContent = setup.connector_configured ?
      'Local connector ready. Register it in your client.' : 'Prepare the connector before opening the MCP client.';
    const status = setup.launchers[launcher.elements.protocol.value === 'save_pi' ? 'pi' : 'codex'];
    find('[data-launcher-status]').textContent = status.available ? 'Custom launcher available in Alloy Studio.' :
      status.custom ? 'Saved launcher is unavailable. Check the executable path.' : 'No custom launcher configured.';
  }

  async function submit(action, status, extra = {}) {
    if (busy) return;
    busy = true;
    notice.classList.remove('error');
    notice.textContent = 'Updating research settings…';
    const buttons = [...panel.querySelectorAll('button')];
    buttons.forEach(button => { button.disabled = true; });
    try {
      setup = await studioPost(endpoint, {action, ...extra});
      render();
      notice.textContent = status;
    } catch (error) {
      notice.textContent = error.message;
      notice.classList.add('error');
    } finally {
      busy = false;
      buttons.forEach(button => { button.disabled = false; });
    }
  }

  find('[data-save-agent]').addEventListener('submit', event => {
    event.preventDefault();
    void submit('save_codex_path', 'Codex path saved.', {executable: codex.value.trim() || null});
  });
  find('[data-agent-action="register_codex"]').addEventListener('click', () => {
    void submit('register_codex', 'Rutile MCP installed. Restart Codex and open a new chat.');
  });
  find('[data-agent-action="prepare_mcp"]').addEventListener('click', () => {
    void submit('prepare_mcp', 'MCP connection ready. Use these settings in your client.');
  });
  find('[data-copy-bridge]').addEventListener('click', async () => {
    if (!setup) return;
    const [command, ...args] = setup.bridge;
    try {
      await navigator.clipboard.writeText(JSON.stringify({mcpServers: {rutile: {command, args}}}, null, 2));
      notice.textContent = 'MCP configuration copied.';
    } catch {
      notice.textContent = 'Copy the executable and arguments from the fields above.';
    }
  });
  launcher.elements.protocol.addEventListener('change', () => { if (setup) render(); });
  launcher.addEventListener('submit', event => {
    event.preventDefault();
    let args;
    try {
      args = JSON.parse(launcher.elements.args.value);
      if (!Array.isArray(args) || args.some(arg => typeof arg !== 'string')) throw new Error();
    } catch {
      notice.textContent = 'Enter the arguments as a JSON array of strings.';
      notice.classList.add('error');
      return;
    }
    void submit(launcher.elements.protocol.value, 'Custom launcher saved.',
      {executable: launcher.elements.executable.value.trim(), args});
  });
  find('[data-clear-launcher]').addEventListener('click', () => {
    void submit(launcher.elements.protocol.value, 'Saved launcher cleared.');
  });

  return {async refresh() {
    if (busy) return;
    try {
      setup = await studioApi(endpoint);
      render();
    } catch (error) {
      notice.classList.add('error');
      notice.textContent = error.message;
    }
  }};
}
