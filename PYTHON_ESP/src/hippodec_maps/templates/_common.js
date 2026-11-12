// Source attribution remains visible alongside each basemap's own credit.
L.Map.addInitHook(function () {
  if (this.attributionControl) this.attributionControl.addAttribution("<a href=\"https://www.miteco.gob.es/\" target=\"_blank\" rel=\"noopener noreferrer\" title=\"© Ministerio para la Transición Ecológica y el Reto Demográfico (MITECO)\">© MITECO</a>");
});

function setupHippoPanels(map) {
  const panels = Array.from(document.querySelectorAll('.hippo-panel'));
  if (!panels.length) return;

  const setCollapsed = (panel, collapsed) => {
    panel.classList.toggle('collapsed', collapsed);
    const button = panel.querySelector('.hippo-panel-toggle');
    if (button) {
      button.textContent = collapsed ? '+' : '−';
      button.title = collapsed ? 'Expandir panel' : 'Minimizar panel';
      button.setAttribute('aria-expanded', String(!collapsed));
    }
  };

  panels.forEach((panel, index) => {
    if (!panel.dataset.panelId) panel.dataset.panelId = 'panel-' + (index + 1);
    const header = panel.querySelector('.hippo-panel-header');
    const button = panel.querySelector('.hippo-panel-toggle');
    if (header && button) {
      L.DomEvent.disableClickPropagation(header);
      button.addEventListener('click', event => {
        event.preventDefault(); event.stopPropagation();
        setCollapsed(panel, !panel.classList.contains('collapsed'));
      });
      header.addEventListener('dblclick', event => {
        if (event.target === button) return;
        event.preventDefault(); event.stopPropagation();
        setCollapsed(panel, !panel.classList.contains('collapsed'));
      });
    }
    if (panel.dataset.startCollapsed === 'true') setCollapsed(panel, true);
    else setCollapsed(panel, false);
    L.DomEvent.disableClickPropagation(panel);
    L.DomEvent.disableScrollPropagation(panel);
  });

  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'panel-manager-trigger';
  trigger.textContent = '☷ Paneles';
  trigger.title = 'Mostrar, ocultar o minimizar paneles';
  trigger.setAttribute('aria-expanded', 'false');

  const menu = document.createElement('div');
  menu.className = 'panel-manager-menu';
  menu.innerHTML = '<div class="panel-manager-title">Paneles visibles</div>';

  panels.forEach(panel => {
    const title = panel.dataset.panelTitle || panel.querySelector('.panel-title')?.textContent || 'Panel';
    const row = document.createElement('label');
    row.className = 'panel-manager-row';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox'; checkbox.checked = true;
    checkbox.dataset.target = panel.dataset.panelId;
    checkbox.addEventListener('change', () => panel.classList.toggle('hippo-panel-hidden', !checkbox.checked));
    row.append(checkbox, document.createTextNode(' ' + title));
    menu.appendChild(row);
  });

  const actions = document.createElement('div');
  actions.className = 'panel-manager-actions';
  const minimize = document.createElement('button');
  minimize.type = 'button'; minimize.className = 'button'; minimize.textContent = 'Minimizar';
  minimize.addEventListener('click', event => { event.stopPropagation(); panels.forEach(panel => setCollapsed(panel, true)); });
  const restore = document.createElement('button');
  restore.type = 'button'; restore.className = 'button'; restore.textContent = 'Mostrar todos';
  restore.addEventListener('click', event => {
    event.stopPropagation();
    panels.forEach(panel => panel.classList.remove('hippo-panel-hidden'));
    menu.querySelectorAll('input[type="checkbox"]').forEach(box => { box.checked = true; });
  });
  actions.append(minimize, restore); menu.appendChild(actions);
  document.body.append(trigger, menu);

  const closeMenu = () => { menu.classList.remove('open'); trigger.setAttribute('aria-expanded', 'false'); };
  trigger.addEventListener('click', event => {
    event.preventDefault(); event.stopPropagation();
    const open = !menu.classList.contains('open');
    menu.classList.toggle('open', open); trigger.setAttribute('aria-expanded', String(open));
  });
  menu.addEventListener('click', event => event.stopPropagation());
  map.on('click', closeMenu);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      closeMenu();
      const credits = document.getElementById('credits-modal');
      if (credits) credits.style.display = 'none';
    }
  });
}

function hippoEncodeState(state) {
  const bytes = new TextEncoder().encode(JSON.stringify(state));
  let binary = '';
  for (let index = 0; index < bytes.length; index += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function hippoDecodeState(value) {
  const padded = String(value).replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((String(value).length + 3) % 4);
  const binary = atob(padded);
  const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
}

function hippoReadState() {
  try {
    const value = new URL(window.location.href).searchParams.get('hippodec_state');
    return value ? hippoDecodeState(value) : null;
  } catch (error) {
    console.warn('No se pudo leer el estado del visor.', error);
    return null;
  }
}

function hippoLinkWithState(link, state) {
  const target = new URL(link, document.baseURI);
  target.searchParams.set('hippodec_state', hippoEncodeState(state));
  return target.href;
}

function hippoCaptureLayers(map) {
  const configuration = window.HIPPODEC_LAYER_CONFIG || {};
  const base = configuration.base || {};
  const overlays = configuration.overlays || {};
  return {
    base: Object.keys(base).find(key => map && map.hasLayer(base[key])) || null,
    overlays: Object.fromEntries(Object.keys(overlays).map(key => [key, Boolean(map && map.hasLayer(overlays[key]))]))
  };
}

function hippoApplyLayers(map, state) {
  if (!map || !state) return;
  const configuration = window.HIPPODEC_LAYER_CONFIG || {};
  const base = configuration.base || {};
  const overlays = configuration.overlays || {};
  if (state.base && base[state.base]) {
    Object.values(base).forEach(layer => { if (map.hasLayer(layer)) map.removeLayer(layer); });
    map.addLayer(base[state.base]);
  }
  if (state.overlays && typeof state.overlays === 'object') {
    Object.entries(overlays).forEach(([key, layer]) => {
      const shouldShow = Boolean(state.overlays[key]);
      if (shouldShow && !map.hasLayer(layer)) map.addLayer(layer);
      if (!shouldShow && map.hasLayer(layer)) map.removeLayer(layer);
    });
  }
}

function hippoCapturePanels() {
  return Object.fromEntries(Array.from(document.querySelectorAll('.hippo-panel')).map(panel => [
    panel.dataset.panelId,
    {collapsed: panel.classList.contains('collapsed'), hidden: panel.classList.contains('hippo-panel-hidden')}
  ]));
}

function hippoApplyPanels(state) {
  if (!state || typeof state !== 'object') return;
  Object.entries(state).forEach(([panelId, settings]) => {
    const panel = Array.from(document.querySelectorAll('.hippo-panel')).find(item => item.dataset.panelId === panelId);
    if (!panel || !settings) return;
    const collapsed = Boolean(settings.collapsed);
    panel.classList.toggle('collapsed', collapsed);
    panel.classList.toggle('hippo-panel-hidden', Boolean(settings.hidden));
    const button = panel.querySelector('.hippo-panel-toggle');
    if (button) {
      button.textContent = collapsed ? '+' : '−';
      button.title = collapsed ? 'Expandir panel' : 'Minimizar panel';
      button.setAttribute('aria-expanded', String(!collapsed));
    }
    const checkbox = Array.from(document.querySelectorAll('.panel-manager-menu input[type="checkbox"]')).find(item => item.dataset.target === panelId);
    if (checkbox) checkbox.checked = !settings.hidden;
  });
}

function hippoCaptureState(map) {
  let custom = {};
  try {
    if (typeof window.HIPPODEC_CAPTURE_STATE === 'function') custom = window.HIPPODEC_CAPTURE_STATE() || {};
  } catch (error) {
    console.warn('No se pudo guardar todo el estado del visor.', error);
  }
  const center = map ? map.getCenter() : null;
  return {
    version: 1,
    map: center ? {center: [center.lat, center.lng], zoom: map.getZoom()} : null,
    layers: map ? hippoCaptureLayers(map) : null,
    panels: hippoCapturePanels(),
    custom
  };
}

function hippoApplyState(map, state) {
  if (!state || typeof state !== 'object') return;
  if (map && state.map && Array.isArray(state.map.center) && Number.isFinite(Number(state.map.zoom))) {
    const latitude = Number(state.map.center[0]);
    const longitude = Number(state.map.center[1]);
    if (Number.isFinite(latitude) && Number.isFinite(longitude)) map.setView([latitude, longitude], Number(state.map.zoom), {animate: false});
  }
  hippoApplyLayers(map, state.layers);
  if (typeof window.HIPPODEC_APPLY_STATE === 'function') window.HIPPODEC_APPLY_STATE(state.custom || {}, state);
  hippoApplyPanels(state.panels);
  if (map) window.setTimeout(() => map.invalidateSize(false), 0);
}

function setupHippoLanguageSwitch(map) {
  const control = document.getElementById('hippodec-language-switch');
  const state = hippoReadState();
  if (state) {
    try { hippoApplyState(map, state); }
    catch (error) { console.warn('No se pudo restaurar el estado del visor.', error); }
  }
  if (!control) return;
  const current = String(control.dataset.current || '').toUpperCase();
  const buttons = Array.from(control.querySelectorAll('[data-language]'));
  buttons.forEach(button => {
    const code = String(button.dataset.language || '').toUpperCase();
    button.setAttribute('aria-pressed', String(code === current));
    button.addEventListener('click', () => {
      if (code === current) return;
      const link = control.dataset[code.toLowerCase() + 'Url'];
      if (!link) return;
      window.location.assign(hippoLinkWithState(link, hippoCaptureState(map)));
    });
  });
}
