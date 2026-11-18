export function initMaterialsSettings() {
  const input = document.getElementById('materials-key');
  const form = document.getElementById('materials-key-form');
  const save = document.getElementById('materials-key-save');
  const clear = document.getElementById('materials-key-clear');
  const status = document.getElementById('materials-key-status');
  let busy = false, clearable = false;

  function message(text, error = false) {
    status.textContent = text;
    status.classList.toggle('error', error);
  }

  async function api(path, options) {
    const response = await fetch(path, options);
    if (!response.ok) throw new Error('Could not update Materials Project settings. Try again.');
    return response.json();
  }

  async function refresh() {
    try {
      const state = await api('/api/materials/status');
      clearable = ['session', 'local_file'].includes(state.source);
      clear.disabled = busy || !clearable;
      message(state.source === 'local_file' ? 'Key saved in Rutile’s local .env.' :
        state.source === 'session' ? 'Key set for this server session.' :
        state.configured ? 'Key configured by the server environment.' : 'No API key configured. Phase calculations work without one.');
    } catch {
      clear.disabled = true;
      message('Could not check key status. Try reopening Settings.', true);
    }
  }

  async function update(key) {
    if (busy) return;
    busy = true;
    input.value = '';
    input.disabled = save.disabled = clear.disabled = true;
    message(key ? 'Saving key…' : 'Clearing saved key…');
    try {
      await api('/api/materials/key', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key, persist: true}),
      });
      busy = false;
      await refresh();
    } catch {
      message('Could not update the key. Check its format and try again.', true);
      clear.disabled = !clearable;
    } finally {
      busy = false;
      input.disabled = save.disabled = false;
    }
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    update(input.value.trim());
  });
  clear.addEventListener('click', () => update(''));
  return {refresh};
}
