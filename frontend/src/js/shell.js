import {createRutileScene} from './rutile-scene.js';
import {initOptimization} from './optimization.js';
import {initMaterialsSettings} from './materials-settings.js';

const canvas = document.getElementById('rutile-scene');
const scene = createRutileScene(canvas, document.getElementById('gem-optics'));
const optimization = initOptimization(family => scene?.setAlloyFamily(family), step => scene?.setOptimizationStep(step));
const materialsSettings = initMaterialsSettings();
const sections = new Map([...document.querySelectorAll('.screen')].map(section =>
  [section.id.slice('screen-'.length), section]
));
const bar = document.getElementById('shell-bar');
const back = document.getElementById('shell-back');
const titleSettings = document.getElementById('title-settings');
const motion = document.getElementById('reduce-motion');
const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
const specimens = document.querySelectorAll('input[name="specimen"]');
const key = 'rutile.appearance';

let screen = 'title';
let returnScreen = 'menu';
let introTimer;
let drag;

function readPreferences() {
  try {
    const value = JSON.parse(localStorage.getItem(key));
    return {specimen: value?.specimen === 'lab' ? 'lab' : 'natural', reduce: value?.reduce === true};
  } catch {
    return {specimen: 'natural', reduce: false};
  }
}

const preferences = readPreferences();

function applyPreferences() {
  const reduce = preferences.reduce || motionPreference.matches;
  document.body.dataset.specimen = preferences.specimen;
  document.body.dataset.motion = reduce ? 'reduced' : 'full';
  scene?.setPreferences(preferences.specimen, reduce);
}

function savePreferences() {
  applyPreferences();
  try {
    localStorage.setItem(key, JSON.stringify(preferences));
  } catch {
    // Settings still apply to the open app when browser storage is unavailable.
  }
}

function show(next, moveFocus = true) {
  clearTimeout(introTimer);
  if (next === 'settings') returnScreen = screen;
  if (next === 'settings') materialsSettings.refresh();
  drag = undefined;
  screen = next;
  document.body.dataset.screen = next;
  document.body.toggleAttribute('data-intro-ready', next === 'loading');
  for (const [name, section] of sections) section.hidden = name !== next;
  bar.hidden = next === 'loading';
  back.hidden = next === 'title';
  titleSettings.hidden = next !== 'title';
  document.body.toggleAttribute('data-dive', scene?.setView(next === 'studio' ? 'menu' : next) === true);
  if (moveFocus) {
    window.scrollTo(0, 0);
    sections.get(next).querySelector('h1')?.focus({preventScroll: true});
  }
}

function goBack() {
  const previous = screen;
  if (previous === 'optimize' && optimization.previousStep()) return;
  if (previous === 'settings') {
    show(returnScreen, false);
    (returnScreen === 'title' ? titleSettings : document.getElementById('menu-settings')).focus();
  } else if (previous === 'optimize') {
    show('studio');
    document.getElementById(`studio-${optimization.mode}`).focus({preventScroll: true});
  } else if (previous === 'diagrams' || previous === 'studio') {
    show('menu', false);
    window.scrollTo(0, 0);
    document.getElementById(previous === 'studio' ? 'menu-optimize' : `menu-${previous}`).focus({preventScroll: true});
  } else {
    show('title');
  }
}

for (const button of document.querySelectorAll('[data-open]')) {
  button.addEventListener('click', () => {
    if (button.dataset.alloyMode) optimization.setMode(button.dataset.alloyMode);
    show(button.dataset.open);
  });
}
for (const button of document.querySelectorAll('.glass-button:not(:disabled)')) {
  button.addEventListener('pointermove', event => {
    if (event.pointerType === 'touch' || document.body.dataset.motion === 'reduced') return;
    const bounds = button.getBoundingClientRect();
    button.style.setProperty('--edge-x', `${(event.clientX - bounds.left) / bounds.width * 100}%`);
    button.style.setProperty('--edge-y', `${(event.clientY - bounds.top) / bounds.height * 100}%`);
  });
  button.addEventListener('pointerleave', () => {
    button.style.removeProperty('--edge-x');
    button.style.removeProperty('--edge-y');
  });
}
back.addEventListener('click', goBack);
for (const input of specimens) {
  input.checked = input.value === preferences.specimen;
  input.addEventListener('change', () => {
    preferences.specimen = input.value;
    savePreferences();
  });
}
motion.checked = preferences.reduce;
motion.addEventListener('change', () => {
  preferences.reduce = motion.checked;
  savePreferences();
});
motionPreference.addEventListener('change', () => {
  applyPreferences();
  if (motionPreference.matches && screen === 'loading') show('title');
});

document.addEventListener('keydown', event => {
  if (event.defaultPrevented || event.repeat || event.altKey || event.ctrlKey || event.metaKey) return;
  const activation = event.key === 'Enter' || event.key === ' ';
  if (activation && event.target.closest('button')) return;
  const arrows = {ArrowLeft: [-25, 0], ArrowRight: [25, 0], ArrowUp: [0, 25], ArrowDown: [0, -25]};
  if ((screen === 'title' || screen === 'menu') && scene && Object.hasOwn(arrows, event.key)) {
    event.preventDefault();
    scene.rotate(...arrows[event.key]);
  } else if ((screen === 'loading' || screen === 'title') && (event.key.length === 1 || activation)) {
    event.preventDefault();
    show(screen === 'loading' ? 'title' : 'menu');
  } else if (event.key === 'Escape' && screen !== 'title' &&
      !event.target.closest('input, select, #plot')) {
    event.preventDefault();
    goBack();
  }
});

if (scene) {
  canvas.addEventListener('pointerdown', event => {
    if (!['title', 'menu'].includes(screen) || drag || event.button !== 0) return;
    canvas.setPointerCapture(event.pointerId);
    drag = {id: event.pointerId, x: event.clientX, y: event.clientY};
  });
  canvas.addEventListener('pointermove', event => {
    if (drag?.id !== event.pointerId) return;
    scene.rotate(event.clientX - drag.x, drag.y - event.clientY);
    drag.x = event.clientX;
    drag.y = event.clientY;
  });
  canvas.addEventListener('lostpointercapture', event => {
    if (drag?.id === event.pointerId) drag = undefined;
  });
} else {
  document.getElementById('rotation-hint').hidden = true;
}

applyPreferences();
if (preferences.reduce || motionPreference.matches) {
  show('title', false);
} else {
  show('loading', false);
  introTimer = setTimeout(() => show('title'), 1000);
}
