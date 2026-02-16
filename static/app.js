// LPWAN Simulator — comprehensive rewrite
"use strict";

const canvas = document.getElementById('grid-canvas');
const ctx = canvas.getContext('2d');
const statusEl = document.getElementById('status');
const container = document.getElementById('canvas-container');

// ═══════════════════════════════════════════════════════════════════════
// State
// ═══════════════════════════════════════════════════════════════════════
let devices = [];
let obstacles = [];
let selectedType = null;   // device or obstacle type string to place
let heatmapData = null;
let propToggle = false;

let zoom = 1.0;
const MIN_ZOOM = 0.25, MAX_ZOOM = 10.0;

let gridCfg = { width_km: 1, height_km: 1, resolution_m: 10 };

let showHalow = true, showLorawan = true, showNbiot = true, showInterference = true, showObstacleAtt = true;
let shadowFading = true, multipathFading = false;

let idCounter = 0;
function nextId(prefix) { return prefix + '_' + (++idCounter); }

// Per-type counters for numbered labels
let labelCounters = {
    halow_ap: 0, halow_endpoint: 0,
    lorawan_gateway: 0, lorawan_endpoint: 0,
    nbiot_base: 0, nbiot_endpoint: 0,
    power_meter: 0,
};

// ═══════════════════════════════════════════════════════════════════════
// Readable labels (with tech prefix)
// ═══════════════════════════════════════════════════════════════════════
const READABLE_LABEL = {
    halow_ap: 'HaLow Access Point',
    halow_endpoint: 'HaLow Endpoint',
    lorawan_gateway: 'LoRaWAN Gateway',
    lorawan_endpoint: 'LoRaWAN Endpoint',
    nbiot_base: 'NB-IoT Cellular Module',
    nbiot_endpoint: 'NB-IoT Endpoint',
    power_meter: 'Power Meter',
};

const DEVICE_COLORS = {
    halow_ap:'#00ffff', halow_endpoint:'#00aaaa',
    lorawan_gateway:'#ff00ff', lorawan_endpoint:'#aa00aa',
    nbiot_base:'#ffaa00', nbiot_endpoint:'#aa6600',
    power_meter:'#ff3333',
};
const OBS_COLORS = { wall:'#666666', house:'#8B4513', water:'#0066cc', forest:'#228B22', water_tower:'#4682B4' };
const OBS_ICONS = { wall:'🧱', house:'🏠', water:'💧', forest:'🌲', water_tower:'🗼' };

// Obstacle types that can be placed
const OBSTACLE_TYPES = ['wall','house','water','forest','water_tower'];

// ═══════════════════════════════════════════════════════════════════════
// Mouse state machine
// ═══════════════════════════════════════════════════════════════════════
// Heatmap cache
let heatmapCache = null;  // offscreen canvas
let heatmapCacheDirty = true;

// RAF throttle
let redrawPending = false;
function requestRedraw() {
    if (!redrawPending) {
        redrawPending = true;
        requestAnimationFrame(() => { redrawPending = false; redraw(); });
    }
}

let mouseState = 'idle';
let dragTarget = null;
let resizeTarget = null;
let tempObs = null;
let obsDrawStart = null;
let measureStart = null;
let measureEnd = null;
let mouseDownPos = null;
let didMove = false;
let measuringActive = false;

// ═══════════════════════════════════════════════════════════════════════
// HaLow channel map
// ═══════════════════════════════════════════════════════════════════════
const HALOW_CHANNELS = {
    1: [1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41,43,45,47,49,51],
    2: [2,6,10,14,18,22,26,30,34,38,42,46,50],
    4: [4,12,20,28,36,44],
};
function halowFreq(ch) { return 902 + ch * 0.5; }

function populateHalowChannels() {
    const sel = document.getElementById('halow-channel');
    const bw = parseInt(document.getElementById('halow-chwidth').value);
    const chs = HALOW_CHANNELS[bw] || HALOW_CHANNELS[2];
    sel.innerHTML = '';
    chs.forEach(ch => {
        const o = document.createElement('option');
        o.value = ch; o.textContent = `Ch ${ch} (${halowFreq(ch).toFixed(1)} MHz)`;
        sel.appendChild(o);
    });
    updateHalowFreqDisplay();
}
function updateHalowFreqDisplay() {
    const ch = parseInt(document.getElementById('halow-channel').value) || 2;
    document.getElementById('halow-freq').textContent = `Center: ${halowFreq(ch).toFixed(1)} MHz`;
}
document.getElementById('halow-chwidth').addEventListener('change', populateHalowChannels);
document.getElementById('halow-channel').addEventListener('change', updateHalowFreqDisplay);

// ═══════════════════════════════════════════════════════════════════════
// LoRaWAN data rate calc
// ═══════════════════════════════════════════════════════════════════════
const LORA_DATARATES = {
    125: {7:5.47,8:3.13,9:1.76,10:0.98,11:0.54,12:0.29},
    250: {7:10.94,8:6.25,9:3.52,10:1.95,11:1.07,12:0.59},
    500: {7:21.88,8:12.50,9:7.03,10:3.91,11:2.15,12:1.17},
};
function updateLoraDatarate() {
    const bw = parseInt(document.getElementById('lora-bw').value);
    const sf = parseInt(document.getElementById('lora-sf').value);
    const dr = (LORA_DATARATES[bw]||{})[sf] || 0;
    document.getElementById('lora-datarate').textContent = `Data Rate: ~${dr} kbps`;
}
document.getElementById('lora-bw').addEventListener('change', updateLoraDatarate);
document.getElementById('lora-sf').addEventListener('change', updateLoraDatarate);
document.getElementById('lora-region').addEventListener('change', updateLoraDatarate);

// ═══════════════════════════════════════════════════════════════════════
// Config panel toggles
// ═══════════════════════════════════════════════════════════════════════
document.querySelectorAll('.config-toggle').forEach(t => {
    t.addEventListener('click', e => {
        e.stopPropagation();
        const panel = document.getElementById(t.dataset.panel);
        if (panel) panel.classList.toggle('open');
    });
});

// ═══════════════════════════════════════════════════════════════════════
// Canvas sizing
// ═══════════════════════════════════════════════════════════════════════
// Grid opacity (0-1), controlled by slider
let gridOpacity = 0.8;

function setupCanvas() {
    const dpr = window.devicePixelRatio || 1;
    // At zoom=1, fill the viewport so 1km grid uses full screen
    const viewW = container.clientWidth || 800;
    const viewH = container.clientHeight || 600;
    const pxPerKm = Math.min(viewW / gridCfg.width_km, viewH / gridCfg.height_km);
    const baseW = gridCfg.width_km * pxPerKm;
    const baseH = gridCfg.height_km * pxPerKm;
    // Store for coordinate conversions
    window._pxPerKm = pxPerKm;
    const w = baseW * zoom;
    const h = baseH * zoom;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    // Center grid in viewport when smaller than container
    const ml = Math.max(0, (viewW - w) / 2);
    const mt = Math.max(0, (viewH - h) / 2);
    canvas.style.marginLeft = ml + 'px';
    canvas.style.marginTop = mt + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    redraw();
}

// ═══════════════════════════════════════════════════════════════════════
// Coordinate conversions — Y increases DOWNWARD (screen-style)
// Top-left = (0,0), bottom-right = (width_km, height_km)
// ═══════════════════════════════════════════════════════════════════════
function ppk() { return window._pxPerKm || 120; }
function screenToKm(clientX, clientY) {
    const r = canvas.getBoundingClientRect();
    const px = clientX - r.left;
    const py = clientY - r.top;
    return { x: px / (ppk() * zoom), y: py / (ppk() * zoom) };
}
function screenToPx(clientX, clientY) {
    const r = canvas.getBoundingClientRect();
    return { x: clientX - r.left, y: clientY - r.top };
}
function kmToPx(xKm, yKm) {
    return { x: xKm * ppk() * zoom, y: yKm * ppk() * zoom };
}

// ═══════════════════════════════════════════════════════════════════════
// Palette buttons — tool stays active after placement
// ═══════════════════════════════════════════════════════════════════════
function deselectAll() {
    document.querySelectorAll('.device-btn,.obstacle-btn').forEach(b => b.classList.remove('active'));
    selectedType = null;
    if (mouseState !== 'measuring') mouseState = 'idle';
    document.getElementById('wall-material').classList.remove('active');
}

document.querySelectorAll('.device-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        deselectAll();
        measuringActive = false;
        mouseState = 'idle';
        btn.classList.add('active');
        selectedType = btn.dataset.type;
        statusEl.textContent = `Click grid to place ${btn.textContent.trim()} (keep clicking to place more, Esc to deselect)`;
    });
});
document.querySelectorAll('.obstacle-btn').forEach(btn => {
    if (btn.id === 'measure-tool') return;
    btn.addEventListener('click', () => {
        deselectAll();
        measuringActive = false;
        mouseState = 'idle';
        btn.classList.add('active');
        selectedType = btn.dataset.type;
        if (selectedType === 'wall') document.getElementById('wall-material').classList.add('active');
        statusEl.textContent = `Click & drag to draw ${btn.textContent.trim()} (keep drawing more, Esc to deselect)`;
    });
});

// Escape key to deselect tool
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        deselectAll();
        measuringActive = false;
        measureStart = measureEnd = null;
        mouseState = 'idle';
        statusEl.textContent = 'Tool deselected';
        redraw();
    }
});

// Toggle measure on/off
document.getElementById('measure-tool').addEventListener('click', () => {
    if (measuringActive) {
        // Deactivate
        measuringActive = false;
        mouseState = 'idle';
        measureStart = measureEnd = null;
        document.getElementById('measure-tool').classList.remove('active');
        statusEl.textContent = 'Measure tool off';
        redraw();
    } else {
        deselectAll();
        measuringActive = true;
        document.getElementById('measure-tool').classList.add('active');
        mouseState = 'measuring';
        measureStart = measureEnd = null;
        statusEl.textContent = 'Click two points to measure (snaps to devices & obstacles). Esc to deselect.';
    }
});

// ═══════════════════════════════════════════════════════════════════════
// Grid controls
// ═══════════════════════════════════════════════════════════════════════
document.getElementById('grid-width').addEventListener('change', e => { gridCfg.width_km = parseInt(e.target.value)||1; setupCanvas(); });
document.getElementById('grid-height').addEventListener('change', e => { gridCfg.height_km = parseInt(e.target.value)||1; setupCanvas(); });
document.getElementById('resolution').addEventListener('change', e => { gridCfg.resolution_m = parseFloat(e.target.value)||10; });

container.addEventListener('wheel', e => {
    e.preventDefault();
    if (e.deltaY > 0) zoom /= 1.1; else zoom *= 1.1;
    zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom));
    document.getElementById('zoom-level').textContent = Math.round(zoom*100)+'%';
    setupCanvas();
    if (mapEnabled && leafletMap) {
        // Map zoom: base zoom at zoom=1, increase proportionally
        const baseZoom = leafletMap._baseZoom || leafletMap.getZoom();
        if (!leafletMap._baseZoom) leafletMap._baseZoom = leafletMap.getZoom();
        const newMapZoom = leafletMap._baseZoom + Math.log2(zoom);
        leafletMap.setZoom(Math.max(1, Math.min(20, newMapZoom)), { animate: false });
    }
}, { passive: false });

document.getElementById('toggle-prop').addEventListener('click', () => {
    propToggle = !propToggle;
    document.getElementById('toggle-prop').textContent = propToggle ? 'Hide Prop' : 'Propagation';
    redraw();
});

// ═══════════════════════════════════════════════════════════════════════
// Hit testing helpers
// ═══════════════════════════════════════════════════════════════════════
function nearestDevice(km, threshKm) {
    let best = null, bestD = threshKm;
    for (const d of devices) {
        const dx = d.position.x - km.x, dy = d.position.y - km.y;
        const dist = Math.sqrt(dx*dx + dy*dy);
        if (dist < bestD) { bestD = dist; best = d; }
    }
    return best;
}

// Snap to obstacle corners and edge midpoints
function nearestObstacleSnapPoint(km, threshKm) {
    let best = null, bestD = threshKm;
    for (const o of obstacles) {
        const x1 = o.position.x, y1 = o.position.y;
        const x2 = x1 + o.width_km, y2 = y1 + o.height_km;
        const mx = (x1+x2)/2, my = (y1+y2)/2;
        // 4 corners + 4 edge midpoints
        const pts = [
            {x:x1,y:y1}, {x:x2,y:y1}, {x:x1,y:y2}, {x:x2,y:y2},
            {x:mx,y:y1}, {x:mx,y:y2}, {x:x1,y:my}, {x:x2,y:my},
        ];
        for (const p of pts) {
            const dx = p.x - km.x, dy = p.y - km.y;
            const dist = Math.sqrt(dx*dx + dy*dy);
            if (dist < bestD) { bestD = dist; best = p; }
        }
    }
    return best;
}

function deviceAtScreen(cx, cy) {
    for (const d of devices) {
        const p = kmToPx(d.position.x, d.position.y);
        if (Math.abs(cx - p.x) < 16 && Math.abs(cy - p.y) < 16) return d;
    }
    return null;
}

function obstacleAtScreen(cx, cy) {
    for (let i = obstacles.length - 1; i >= 0; i--) {
        const o = obstacles[i];
        const tl = kmToPx(o.position.x, o.position.y);
        const w = o.width_km * ppk() * zoom, h = o.height_km * ppk() * zoom;
        if (cx >= tl.x && cx <= tl.x + w && cy >= tl.y && cy <= tl.y + h) return o;
    }
    return null;
}

function resizeHandleAt(cx, cy) {
    for (let i = obstacles.length - 1; i >= 0; i--) {
        const o = obstacles[i];
        const br = kmToPx(o.position.x + o.width_km, o.position.y + o.height_km);
        if (Math.abs(cx - br.x) < 10 && Math.abs(cy - br.y) < 10) return o;
    }
    return null;
}

// ═══════════════════════════════════════════════════════════════════════
// Build device object with current config
// ═══════════════════════════════════════════════════════════════════════
function makeDevice(type, km) {
    labelCounters[type] = (labelCounters[type] || 0) + 1;
    const d = {
        id: nextId(type),
        type: type,
        position: { x: km.x, y: km.y },
        label: (READABLE_LABEL[type] || type) + ' ' + labelCounters[type],
    };
    if (type.startsWith('halow')) {
        d.channel_width_mhz = parseFloat(document.getElementById('halow-chwidth').value);
        d.channel = parseInt(document.getElementById('halow-channel').value);
        d.mcs = 2;
        d.elevation_m = parseFloat(document.getElementById('halow-elevation').value) || 3;
        if (type === 'halow_ap') { d.tx_power_dbm = 30; d.antenna_gain_dbi = 3; }
        else { d.tx_power_dbm = 10; }
    } else if (type.startsWith('lorawan')) {
        d.region = document.getElementById('lora-region').value;
        d.spreading_factor = parseInt(document.getElementById('lora-sf').value);
        d.bandwidth_khz = parseFloat(document.getElementById('lora-bw').value);
        const elVal = parseFloat(document.getElementById('lorawan-elevation').value);
        if (type === 'lorawan_gateway') { d.antenna_gain_dbi = 6; d.elevation_m = elVal || 15; }
        else { d.tx_power_dbm = 14; d.elevation_m = 1; }
    } else if (type.startsWith('nbiot')) {
        d.band = 'B5';
        d.tone_mode = 'single-15';
        if (type === 'nbiot_base') { d.antenna_gain_dbi = 8; }
        else { d.tx_power_dbm = 23; }
    } else if (type === 'power_meter') {
        d.tx_power_dbm = 20;
        d.frequency_mhz = 925;
        d.bandwidth_khz = 50000; // 50 MHz wide
        d.propagation_radius_m = 50;
    }
    return d;
}

// ═══════════════════════════════════════════════════════════════════════
// Mouse handlers
// ═══════════════════════════════════════════════════════════════════════
canvas.addEventListener('mousedown', e => {
    if (e.button === 2) return; // right-click handled separately
    const {x: cx, y: cy} = screenToPx(e.clientX, e.clientY);
    const km = screenToKm(e.clientX, e.clientY);
    mouseDownPos = { x: e.clientX, y: e.clientY };
    didMove = false;

    if (mouseState === 'measuring') {
        // Snap threshold scales with zoom: 15px on screen
        const snapThreshKm = 15 / (ppk() * zoom);
        const snapDev = nearestDevice(km, snapThreshKm);
        const snapObs = nearestObstacleSnapPoint(km, snapThreshKm);
        // Pick closest of device vs obstacle snap
        let pt = km;
        let bestDist = Infinity;
        if (snapDev) {
            const dd = Math.hypot(snapDev.position.x - km.x, snapDev.position.y - km.y);
            if (dd < bestDist) { bestDist = dd; pt = { x: snapDev.position.x, y: snapDev.position.y }; }
        }
        if (snapObs) {
            const dd = Math.hypot(snapObs.x - km.x, snapObs.y - km.y);
            if (dd < bestDist) { bestDist = dd; pt = snapObs; }
        }
        if (!measureStart) {
            measureStart = pt;
            measureEnd = null;
            statusEl.textContent = 'Click second point (snaps to devices & obstacles)';
        } else {
            measureEnd = pt;
            const dx = measureEnd.x - measureStart.x, dy = measureEnd.y - measureStart.y;
            const distM = Math.sqrt(dx*dx + dy*dy) * 1000;
            statusEl.textContent = `Distance: ${formatDistance(distM)}`;
        }
        redraw();
        return;
    }

    const rh = resizeHandleAt(cx, cy);
    if (rh) { mouseState = 'resizing'; resizeTarget = rh; return; }

    const dev = deviceAtScreen(cx, cy);
    if (dev) { mouseState = 'dragging'; dragTarget = dev; return; }

    const obs = obstacleAtScreen(cx, cy);
    if (obs && !selectedType) { mouseState = 'dragging'; dragTarget = obs; dragTarget._dragOff = { x: km.x - obs.position.x, y: km.y - obs.position.y }; return; }

    if (selectedType && OBSTACLE_TYPES.includes(selectedType)) {
        mouseState = 'drawing-obs';
        obsDrawStart = { x: clampX(km.x), y: clampY(km.y) };
        tempObs = {
            id: nextId(selectedType),
            type: selectedType,
            position: { x: clampX(km.x), y: clampY(km.y) },
            width_km: 0, height_km: 0,
            material: selectedType === 'wall' ? document.getElementById('wall-mat').value : selectedType,
        };
        return;
    }

    if (selectedType && DEVICE_COLORS[selectedType]) {
        mouseState = 'placing';
        return;
    }

    if (obs) { mouseState = 'dragging'; dragTarget = obs; dragTarget._dragOff = { x: km.x - obs.position.x, y: km.y - obs.position.y }; return; }
});

canvas.addEventListener('mousemove', e => {
    const km = screenToKm(e.clientX, e.clientY);
    if (mouseDownPos) {
        const dx = e.clientX - mouseDownPos.x, dy = e.clientY - mouseDownPos.y;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) didMove = true;
    }

    if (mouseState === 'dragging' && dragTarget) {
        if (dragTarget.type && DEVICE_COLORS[dragTarget.type]) {
            dragTarget.position.x = clampX(km.x);
            dragTarget.position.y = clampY(km.y);
        } else {
            const off = dragTarget._dragOff || {x:0,y:0};
            dragTarget.position.x = clampX(km.x - off.x);
            dragTarget.position.y = clampY(km.y - off.y);
        }
        requestRedraw();
        return;
    }

    if (mouseState === 'resizing' && resizeTarget) {
        resizeTarget.width_km = Math.max(0.05, km.x - resizeTarget.position.x);
        resizeTarget.height_km = Math.max(0.05, km.y - resizeTarget.position.y);
        requestRedraw();
        return;
    }

    if (mouseState === 'drawing-obs' && tempObs && obsDrawStart) {
        tempObs.position.x = Math.min(obsDrawStart.x, km.x);
        tempObs.position.y = Math.min(obsDrawStart.y, km.y);
        tempObs.width_km = Math.abs(km.x - obsDrawStart.x);
        tempObs.height_km = Math.abs(km.y - obsDrawStart.y);
        requestRedraw();
        return;
    }

    // Show RSSI at cursor position when simulation is active
    if (heatmapData && heatmapData.rssi_grid && mouseState === 'idle') {
        const { rssi_grid, grid_shape } = heatmapData;
        const [rows, cols] = grid_shape;
        const row = Math.floor(km.y * 1000 / gridCfg.resolution_m);
        const col = Math.floor(km.x * 1000 / gridCfg.resolution_m);
        if (row >= 0 && row < rows && col >= 0 && col < cols) {
            const rssi = rssi_grid[row][col];
            statusEl.textContent = `RSSI: ${rssi.toFixed(1)} dBm  |  Position: (${(km.x).toFixed(3)}km, ${(km.y).toFixed(3)}km)`;
        }
    }
});

canvas.addEventListener('mouseup', e => {
    if (e.button === 2) return;
    const km = screenToKm(e.clientX, e.clientY);

    if (mouseState === 'placing' && !didMove && selectedType && DEVICE_COLORS[selectedType]) {
        const dev = makeDevice(selectedType, km);
        devices.push(dev);
        updateCounts();
        statusEl.textContent = `Placed ${dev.label} — click to place more, Esc to deselect`;
        redraw();
        if (simActive) runSimulation();
    }

    if (mouseState === 'drawing-obs' && tempObs) {
        if (tempObs.width_km > 0.005 && tempObs.height_km > 0.005) {
            obstacles.push(tempObs);
            updateCounts();
            statusEl.textContent = `Placed ${tempObs.type} — drag to draw more, Esc to deselect`;
        }
        tempObs = null; obsDrawStart = null;
        redraw();
        if (simActive) runSimulation();
    }

    if (mouseState === 'dragging') {
        if (dragTarget) delete dragTarget._dragOff;
        statusEl.textContent = 'Moved';
        if (simActive) runSimulation();
    }
    if (mouseState === 'resizing') {
        statusEl.textContent = 'Resized';
        if (simActive) runSimulation();
    }

    if (mouseState !== 'measuring') mouseState = 'idle';
    dragTarget = null; resizeTarget = null; mouseDownPos = null; didMove = false;
});

// Right-click to remove device/obstacle OR deselect tool
canvas.addEventListener('contextmenu', e => {
    e.preventDefault();
    const {x: cx, y: cy} = screenToPx(e.clientX, e.clientY);

    // Check device first
    const dev = deviceAtScreen(cx, cy);
    if (dev) {
        devices = devices.filter(d => d !== dev);
        updateCounts();
        statusEl.textContent = `Removed ${dev.label}`;
        redraw();
        if (simActive) runSimulation();
        return;
    }

    // Check obstacle
    const obs = obstacleAtScreen(cx, cy);
    if (obs) {
        obstacles = obstacles.filter(o => o !== obs);
        updateCounts();
        statusEl.textContent = `Removed ${obs.type}`;
        redraw();
        if (simActive) runSimulation();
        return;
    }

    // Right-click on empty space deselects tool
    deselectAll();
    measuringActive = false;
    measureStart = measureEnd = null;
    mouseState = 'idle';
    statusEl.textContent = 'Tool deselected';
    redraw();
});

function clampX(v) { return Math.max(0, Math.min(gridCfg.width_km, v)); }
function clampY(v) { return Math.max(0, Math.min(gridCfg.height_km, v)); }

// ═══════════════════════════════════════════════════════════════════════
// Distance formatting
// ═══════════════════════════════════════════════════════════════════════
function formatDistance(meters) {
    if (meters < 100) return meters.toFixed(1) + ' m';
    if (meters < 1000) return Math.round(meters) + ' m';
    return (meters / 1000).toFixed(2) + ' km';
}

// ═══════════════════════════════════════════════════════════════════════
// Simulation
// ═══════════════════════════════════════════════════════════════════════
let simActive = false;

async function runSimulation() {
    const filteredDevices = devices.filter(d => {
        if (d.type.startsWith('halow') && !showHalow) return false;
        if (d.type.startsWith('lorawan') && !showLorawan) return false;
        if (d.type.startsWith('nbiot') && !showNbiot) return false;
        if (d.type === 'power_meter' && !showInterference) return false;
        return true;
    });
    const filteredObstacles = showObstacleAtt ? obstacles : [];
    if (filteredDevices.length === 0) {
        heatmapData = null; heatmapCacheDirty = true; redraw();
        statusEl.textContent = 'No visible devices for simulation';
        return;
    }
    statusEl.textContent = 'Running simulation...';
    try {
        const resp = await fetch('/api/simulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                width_km: gridCfg.width_km,
                height_km: gridCfg.height_km,
                resolution_m: gridCfg.resolution_m,
                devices: filteredDevices,
                obstacles: filteredObstacles,
                environment_type: document.getElementById('env-type').value,
                shadow_fading: shadowFading,
                multipath_fading: multipathFading,
            }),
        });
        const data = await resp.json();
        if (data.ok) {
            heatmapData = data.result;
            heatmapCacheDirty = true;
            updateStats(data.result.stats);
            updatePerTechStats(data.result.per_tech_stats || null);
            redraw();
            statusEl.textContent = 'Simulation active - toggle off to hide';
        } else {
            statusEl.textContent = 'Error: ' + data.error;
            console.error('Sim error:', data.error, data.trace);
        }
    } catch (err) {
        statusEl.textContent = 'Error: ' + err.message;
        console.error('Fetch error:', err);
    }
}

document.getElementById('run-sim').addEventListener('click', async () => {
    simActive = !simActive;
    const btn = document.getElementById('run-sim');
    if (simActive) {
        btn.textContent = '■ Stop Simulation';
        btn.style.background = '#cc6600';
        await runSimulation();
    } else {
        btn.textContent = '▶ Run Simulation';
        btn.style.background = '';
        heatmapData = null;
        heatmapCacheDirty = true;
        heatmapCache = null;
        updateStats(null);
        updatePerTechStats(null);
        redraw();
        statusEl.textContent = 'Simulation off';
    }
});

document.getElementById('clear-all').addEventListener('click', () => {
    if (!confirm('Clear everything?')) return;
    devices = []; obstacles = []; heatmapData = null; heatmapCache = null; heatmapCacheDirty = true;
    measureStart = measureEnd = null;
    measuringActive = false;
    simActive = false;
    document.getElementById('run-sim').textContent = '▶ Run Simulation';
    document.getElementById('run-sim').style.background = '';
    labelCounters = { halow_ap:0, halow_endpoint:0, lorawan_gateway:0, lorawan_endpoint:0, nbiot_base:0, nbiot_endpoint:0, power_meter:0 };
    updateCounts(); updateStats(null); updatePerTechStats(null); redraw();
    statusEl.textContent = 'Cleared';
});

// ═══════════════════════════════════════════════════════════════════════
// Drawing
// ═══════════════════════════════════════════════════════════════════════
function redraw() {
    const w = parseFloat(canvas.style.width);
    const h = parseFloat(canvas.style.height);
    ctx.clearRect(0, 0, w, h);
    if (mapEnabled) {
        canvas.style.background = 'transparent';
        container.style.background = 'transparent';
    } else {
        canvas.style.background = '';
        container.style.background = '#1a1a1a';
        ctx.fillStyle = '#1a1a1a';
        ctx.fillRect(0, 0, w, h);
    }
    drawGrid();
    if (heatmapData) drawHeatmap();
    drawObstacles();
    if (tempObs) drawOneObs(tempObs, true);
    if (propToggle) drawPropCircles();
    drawDevices();
    if (measureStart) drawMeasure();
}

function drawGrid() {
    ctx.globalAlpha = gridOpacity;
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 1;
    // X-axis labels (left to right)
    for (let km = 0; km <= gridCfg.width_km; km++) {
        const x = km * ppk() * zoom;
        ctx.beginPath(); ctx.moveTo(x, 0);
        ctx.lineTo(x, gridCfg.height_km * ppk() * zoom); ctx.stroke();
        ctx.fillStyle = '#fff'; ctx.font = `${Math.max(9, 10*zoom)}px monospace`;
        ctx.fillText(km + 'km', x + 2, 12*zoom);
    }
    // Y-axis labels — 0km at top, increasing downward
    for (let km = 0; km <= gridCfg.height_km; km++) {
        const y = km * ppk() * zoom;
        ctx.beginPath(); ctx.moveTo(0, y);
        ctx.lineTo(gridCfg.width_km * ppk() * zoom, y); ctx.stroke();
        ctx.fillStyle = '#fff'; ctx.font = `${Math.max(9, 10*zoom)}px monospace`;
        ctx.fillText(km + 'km', 2, y - 3);
    }
    ctx.globalAlpha = 1;
}

function rebuildHeatmapCache() {
    const { rssi_grid, interference_grid, grid_shape } = heatmapData;
    const [rows, cols] = grid_shape;
    const offscreen = document.createElement('canvas');
    offscreen.width = cols;
    offscreen.height = rows;
    const offCtx = offscreen.getContext('2d');
    const imgData = offCtx.createImageData(cols, rows);
    const d = imgData.data;
    for (let i = 0; i < rows; i++) {
        for (let j = 0; j < cols; j++) {
            const idx = (i * cols + j) * 4;
            const rssi = rssi_grid[i][j];
            const c = rssiColorRGBA(rssi);
            d[idx] = c[0]; d[idx+1] = c[1]; d[idx+2] = c[2]; d[idx+3] = c[3];
        }
    }
    offCtx.putImageData(imgData, 0, 0);
    // Interference overlay pass (composite on top) — only when toggle is ON
    if (interference_grid && showInterference) {
        const offscreen2 = document.createElement('canvas');
        offscreen2.width = cols; offscreen2.height = rows;
        const offCtx2 = offscreen2.getContext('2d');
        const imgData2 = offCtx2.createImageData(cols, rows);
        const d2 = imgData2.data;
        for (let i = 0; i < rows; i++) {
            for (let j = 0; j < cols; j++) {
                const idx = (i * cols + j) * 4;
                const interf = interference_grid[i][j];
                if (interf > -120) {
                    const alpha = Math.min(0.6, Math.max(0.05, (interf + 120) / 80));
                    d2[idx] = 160; d2[idx+1] = 0; d2[idx+2] = 0; d2[idx+3] = Math.round(alpha * 255);
                }
            }
        }
        offCtx2.putImageData(imgData2, 0, 0);
        offCtx.drawImage(offscreen2, 0, 0);
    }
    heatmapCache = offscreen;
    heatmapCacheDirty = false;
}

// Detect dominant tech from placed devices
function getDominantTech() {
    // Only count techs that are toggled ON and have devices placed
    const techs = new Set();
    for (const d of devices) {
        if (d.type.startsWith('halow') && showHalow) techs.add('halow');
        else if (d.type.startsWith('lorawan') && showLorawan) techs.add('lorawan');
        else if (d.type.startsWith('nbiot') && showNbiot) techs.add('nbiot');
    }
    if (techs.size === 1) return [...techs][0];
    if (techs.size === 0) return 'none';
    return 'mixed';
}

function rssiColorRGBA(rssi) {
    const isMap = mapEnabled;
    // High alpha so colors are vivid on dark background
    const mapScale = isMap ? 0.6 : 1.0;
    const aExc  = Math.round(0.85 * mapScale * 255);
    const aGood = Math.round(0.70 * mapScale * 255);
    const aFair = Math.round(0.55 * mapScale * 255);
    const aPoor = Math.round(0.40 * mapScale * 255);
    const tech = getDominantTech();

    if (tech === 'halow') {
        // Bright cyan → teal → blue-teal → deep navy
        if (rssi > -65) return [0,229,229, aExc];     // bright cyan
        if (rssi > -75) return [0,179,179, aGood];    // teal
        if (rssi > -85) return [0,128,160, aFair];    // blue-teal
        return [0,60,120, aPoor];                      // deep blue
    } else if (tech === 'lorawan') {
        // Bright magenta → purple → dark purple → deep purple
        if (rssi > -100) return [255,68,255, aExc];
        if (rssi > -120) return [180,0,180, aGood];
        if (rssi > -130) return [100,0,140, aFair];
        return [50,0,80, aPoor];
    } else if (tech === 'nbiot') {
        // Bright orange → medium orange → pale → faded
        if (rssi > -90) return [255,187,51, aExc];
        if (rssi > -110) return [221,136,0, aGood];
        if (rssi > -120) return [180,130,30, aFair];
        return [130,100,50, aPoor];
    } else {
        // Mixed: use all tech colors based on RSSI range
        if (rssi > -65) return [0,229,229, aExc];
        if (rssi > -85) return [0,179,179, aGood];
        if (rssi > -100) return [180,0,180, aFair];
        if (rssi > -120) return [221,136,0, aPoor];
        return [255,50,50, Math.round(0.30 * mapScale * 255)];
    }
}

function drawHeatmap() {
    if (heatmapCacheDirty || !heatmapCache) rebuildHeatmapCache();
    const w = gridCfg.width_km * ppk() * zoom;
    const h = gridCfg.height_km * ppk() * zoom;
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(heatmapCache, 0, 0, w, h);
    ctx.imageSmoothingEnabled = true;
}

function rssiColor(rssi) {
    const c = rssiColorRGBA(rssi);
    return `rgba(${c[0]},${c[1]},${c[2]},${(c[3]/255).toFixed(2)})`;
}

function drawObstacles() { obstacles.forEach(o => drawOneObs(o, false)); }
function drawOneObs(o, isTemp) {
    const tl = kmToPx(o.position.x, o.position.y);
    const w = o.width_km * ppk() * zoom, h = o.height_km * ppk() * zoom;
    ctx.globalAlpha = isTemp ? 0.5 : 1;

    // Light semi-transparent fill so bounding area is visible
    ctx.fillStyle = OBS_COLORS[o.type] || '#888';
    ctx.globalAlpha = isTemp ? 0.2 : 0.15;
    ctx.fillRect(tl.x, tl.y, w, h);
    ctx.globalAlpha = isTemp ? 0.5 : 1;

    // White border outline
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5;
    ctx.strokeRect(tl.x, tl.y, w, h);

    // Draw icons based on type
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    if (o.type === 'forest') {
        _drawForestTrees(tl.x, tl.y, w, h);
    } else if (o.type === 'water') {
        _drawPond(tl.x, tl.y, w, h);
    } else if (o.type === 'house') {
        _drawHouse(tl.x, tl.y, w, h);
    } else if (o.type === 'wall') {
        _drawWall(tl.x, tl.y, w, h);
    } else if (o.type === 'water_tower') {
        _drawWaterTower(tl.x, tl.y, w, h);
    }
    ctx.textAlign = 'start'; ctx.textBaseline = 'alphabetic';

    // Label
    ctx.fillStyle = '#fff'; ctx.font = `${Math.max(9, 10*zoom)}px sans-serif`;
    const typeNames = { wall:'Wall', house:'House', water:'Water Pond', forest:'Forest', water_tower:'Water Tower' };
    const lbl = (typeNames[o.type] || o.type) + (o.type === 'wall' ? ' (' + o.material + ')' : '');
    ctx.fillText(lbl, tl.x + 4, tl.y + 13*zoom);
    ctx.globalAlpha = 1;
    if (!isTemp) {
        ctx.fillStyle = '#0088ff';
        ctx.fillRect(tl.x + w - 7, tl.y + h - 7, 7, 7);
    }
}

// ── Obstacle icon drawing helpers ──
function _drawForestTrees(x, y, w, h) {
    const treeSize = Math.max(8, Math.min(20, Math.min(w, h) / 4));
    const padding = treeSize * 0.6;
    const cols = Math.max(1, Math.floor((w - padding) / (treeSize * 1.2)));
    const rows = Math.max(1, Math.floor((h - padding) / (treeSize * 1.4)));
    const count = Math.min(cols * rows, 25);
    const xStep = (w - padding * 2) / Math.max(1, cols - 1);
    const yStep = (h - padding * 2) / Math.max(1, rows - 1);
    ctx.fillStyle = '#228B22';
    for (let r = 0; r < rows && r * cols < count; r++) {
        for (let c = 0; c < cols && r * cols + c < count; c++) {
            const tx = x + padding + c * xStep + (r % 2 ? xStep * 0.3 : 0);
            const ty = y + padding + r * yStep;
            // Triangle tree
            ctx.beginPath();
            ctx.moveTo(tx, ty - treeSize * 0.6);
            ctx.lineTo(tx + treeSize * 0.4, ty + treeSize * 0.3);
            ctx.lineTo(tx - treeSize * 0.4, ty + treeSize * 0.3);
            ctx.closePath();
            ctx.fill();
            // Trunk
            ctx.fillStyle = '#8B4513';
            ctx.fillRect(tx - treeSize * 0.08, ty + treeSize * 0.3, treeSize * 0.16, treeSize * 0.2);
            ctx.fillStyle = '#228B22';
        }
    }
}

function _drawPond(x, y, w, h) {
    const cx = x + w / 2, cy = y + h / 2;
    const rx = w * 0.4, ry = h * 0.35;
    // Water fill
    ctx.fillStyle = 'rgba(0, 102, 204, 0.5)';
    ctx.beginPath();
    ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
    ctx.fill();
    // Shore outline
    ctx.strokeStyle = '#004488'; ctx.lineWidth = 1.5;
    ctx.stroke();
    // Ripple lines
    ctx.strokeStyle = 'rgba(255,255,255,0.3)'; ctx.lineWidth = 1;
    for (let i = -1; i <= 1; i++) {
        ctx.beginPath();
        ctx.ellipse(cx, cy + i * ry * 0.3, rx * 0.5, ry * 0.12, 0, 0, Math.PI);
        ctx.stroke();
    }
}

function _drawHouse(x, y, w, h) {
    const cx = x + w / 2, cy = y + h / 2;
    const hw = Math.min(w, h) * 0.35;
    // House body
    ctx.fillStyle = '#8B4513';
    ctx.fillRect(cx - hw * 0.8, cy - hw * 0.2, hw * 1.6, hw * 1.0);
    // Roof
    ctx.fillStyle = '#A52A2A';
    ctx.beginPath();
    ctx.moveTo(cx, cy - hw * 0.8);
    ctx.lineTo(cx + hw, cy - hw * 0.2);
    ctx.lineTo(cx - hw, cy - hw * 0.2);
    ctx.closePath();
    ctx.fill();
    // Door
    ctx.fillStyle = '#DEB887';
    ctx.fillRect(cx - hw * 0.15, cy + hw * 0.2, hw * 0.3, hw * 0.6);
    // Window
    ctx.fillStyle = '#87CEEB';
    ctx.fillRect(cx + hw * 0.25, cy, hw * 0.3, hw * 0.25);
    ctx.fillRect(cx - hw * 0.55, cy, hw * 0.3, hw * 0.25);
}

function _drawWall(x, y, w, h) {
    // Brick pattern
    const bw = Math.max(6, Math.min(16, w / 6));
    const bh = bw * 0.5;
    ctx.fillStyle = '#999';
    let row = 0;
    for (let by = y + 2; by < y + h - 2; by += bh + 1) {
        const offset = (row % 2) ? bw * 0.5 : 0;
        for (let bx = x + 2 + offset; bx < x + w - 2; bx += bw + 1) {
            const bWidth = Math.min(bw, x + w - 2 - bx);
            if (bWidth > 2) {
                ctx.fillRect(bx, by, bWidth, bh);
            }
        }
        row++;
    }
}

function _drawWaterTower(x, y, w, h) {
    const cx = x + w / 2, cy = y + h / 2;
    const sz = Math.min(w, h) * 0.3;
    // Legs
    ctx.strokeStyle = '#888'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(cx - sz * 0.6, cy + sz * 1.2); ctx.lineTo(cx - sz * 0.3, cy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx + sz * 0.6, cy + sz * 1.2); ctx.lineTo(cx + sz * 0.3, cy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx, cy + sz * 1.2); ctx.lineTo(cx, cy); ctx.stroke();
    // Tank
    ctx.fillStyle = '#4682B4';
    ctx.beginPath();
    ctx.ellipse(cx, cy - sz * 0.3, sz * 0.6, sz * 0.5, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 1;
    ctx.stroke();
}

// Propagation colors per technology
const PROP_COLORS = {
    halow: 'rgba(0,230,230,',
    lorawan: 'rgba(200,0,200,',
    nbiot: 'rgba(255,170,0,',
    power_meter: 'rgba(255,51,51,',
};

function getTechKey(type) {
    if (type.startsWith('halow')) return 'halow';
    if (type.startsWith('lorawan')) return 'lorawan';
    if (type.startsWith('nbiot')) return 'nbiot';
    if (type === 'power_meter') return 'power_meter';
    return 'halow';
}

function drawPropCircles() {
    devices.forEach(d => {
        const p = kmToPx(d.position.x, d.position.y);
        let rangeKm;
        if (d.type === 'power_meter') rangeKm = 0.05;
        else if (d.type.includes('lorawan')) rangeKm = 10;
        else if (d.type.includes('nbiot')) rangeKm = 8;
        else rangeKm = 1;

        const techKey = getTechKey(d.type);
        const colorBase = PROP_COLORS[techKey] || 'rgba(255,255,255,';
        ctx.lineWidth = 1.2;
        for (let r = 0.5; r <= rangeKm; r += 0.5) {
            ctx.strokeStyle = colorBase + '0.18)';
            ctx.beginPath(); ctx.arc(p.x, p.y, r * ppk() * zoom, 0, Math.PI*2); ctx.stroke();
        }
    });
}

function drawDevices() {
    const sz = 10;
    const fontSize = Math.max(8, 10);
    devices.forEach(d => {
        const p = kmToPx(d.position.x, d.position.y);
        ctx.fillStyle = DEVICE_COLORS[d.type]; ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5;
        if (d.type.includes('gateway') || d.type.includes('ap') || d.type.includes('base')) {
            ctx.fillRect(p.x-sz/2, p.y-sz/2, sz, sz);
            ctx.strokeRect(p.x-sz/2, p.y-sz/2, sz, sz);
        } else if (d.type === 'power_meter') {
            ctx.beginPath();
            ctx.moveTo(p.x, p.y - sz/2);
            ctx.lineTo(p.x + sz/2, p.y);
            ctx.lineTo(p.x, p.y + sz/2);
            ctx.lineTo(p.x - sz/2, p.y);
            ctx.closePath();
            ctx.fill(); ctx.stroke();
        } else {
            ctx.beginPath(); ctx.arc(p.x, p.y, sz/2, 0, Math.PI*2); ctx.fill(); ctx.stroke();
        }
        ctx.fillStyle = '#fff'; ctx.font = `${fontSize}px sans-serif`;
        ctx.fillText(d.label, p.x + sz, p.y + 4);
    });
    // Draw RSSI link labels between gateway/AP and endpoints of same tech
    if (heatmapData && heatmapData.rssi_grid) drawRssiLinks();
}

// Compute RSSI from a gateway/AP to an endpoint using log-distance path loss
function computeLinkRssi(gw, ep) {
    const dx = (gw.position.x - ep.position.x) * 1000; // meters
    const dy = (gw.position.y - ep.position.y) * 1000;
    const dist = Math.sqrt(dx*dx + dy*dy);
    if (dist < 1) return 0; // co-located
    
    // Get frequency
    let freqMhz = 903; // default HaLow
    if (gw.type.startsWith('lorawan')) {
        freqMhz = gw.region === 'EU868' ? 868 : 915;
    } else if (gw.type.startsWith('nbiot')) {
        freqMhz = 869;
    } else if (gw.type.startsWith('halow')) {
        freqMhz = 902 + (gw.channel || 2) * 0.5;
    }
    
    // Path loss exponent from environment selector
    const envSel = document.getElementById('env-type');
    const envMap = { urban: 2.7, suburban: 2.4, rural: 2.0 };
    const n = envMap[envSel ? envSel.value : 'urban'] || 2.7;
    
    // FSPL at d0=1m: 20*log10(d0_km) + 20*log10(f) + 32.44
    const d0 = 1.0;
    const pl0 = 20 * Math.log10(d0/1000) + 20 * Math.log10(freqMhz) + 32.44;
    const pl = pl0 + 10 * n * Math.log10(dist / d0);
    
    // TX power + antenna gain
    const txPower = gw.tx_power_dbm || 30;
    const gain = gw.antenna_gain_dbi || 3;
    const heightGain = (gw.elevation_m && gw.elevation_m > 1) ? 6 * Math.log10(gw.elevation_m) / Math.log10(10) : 0;
    
    // Obstacle attenuation (approximate: check if any obstacle bbox intersects the link line)
    let obsAtt = 0;
    if (showObstacleAtt) {
        for (const o of obstacles) {
            const ox = o.position.x * 1000, oy = o.position.y * 1000;
            const ow = o.width_km * 1000, oh = o.height_km * 1000;
            if (_lineIntersectsRect(gw.position.x*1000, gw.position.y*1000, ep.position.x*1000, ep.position.y*1000, ox, oy, ow, oh)) {
                const matAtt = {wood:4, glass:3, cement:12, metal:25, house:10, water:12, forest:8, water_tower:15};
                obsAtt += matAtt[o.material] || matAtt[o.type] || 10;
            }
        }
    }
    
    return txPower + gain + heightGain - pl - obsAtt;
}

// Simple line-rect intersection for link RSSI calculation
function _lineIntersectsRect(x1,y1,x2,y2,rx,ry,rw,rh) {
    // Parametric ray test against 4 edges
    const dx = x2-x1, dy = y2-y1;
    const edges = [
        [rx,ry, rx+rw,ry], [rx+rw,ry, rx+rw,ry+rh],
        [rx+rw,ry+rh, rx,ry+rh], [rx,ry+rh, rx,ry]
    ];
    for (const [ex1,ey1,ex2,ey2] of edges) {
        const edx = ex2-ex1, edy = ey2-ey1;
        const denom = dx*edy - dy*edx;
        if (Math.abs(denom) < 1e-10) continue;
        const t = ((ex1-x1)*edy - (ey1-y1)*edx) / denom;
        const u = ((ex1-x1)*dy - (ey1-y1)*dx) / denom;
        if (t > 0.01 && t < 0.99 && u >= 0 && u <= 1) return true;
    }
    return false;
}

function drawRssiLinks() {
    const gateways = devices.filter(d => d.type.includes('gateway') || d.type.includes('ap') || d.type.includes('base'));
    const endpoints = devices.filter(d => d.type.includes('endpoint'));
    
    function sameTech(a, b) {
        const ta = a.type.split('_')[0], tb = b.type.split('_')[0];
        return ta === tb;
    }
    
    const linkFontSize = Math.max(9, 11 / zoom);
    ctx.font = `bold ${linkFontSize}px monospace`;
    
    for (const gw of gateways) {
        for (const ep of endpoints) {
            if (!sameTech(gw, ep)) continue;
            
            // Compute RSSI analytically (gateway → endpoint)
            const rssi = computeLinkRssi(gw, ep);
            
            const gp = kmToPx(gw.position.x, gw.position.y);
            const ep_px = kmToPx(ep.position.x, ep.position.y);
            
            // Draw dashed link line
            ctx.strokeStyle = 'rgba(255,255,255,0.3)';
            ctx.lineWidth = 1 / zoom;
            ctx.setLineDash([3/zoom, 3/zoom]);
            ctx.beginPath(); ctx.moveTo(gp.x, gp.y); ctx.lineTo(ep_px.x, ep_px.y); ctx.stroke();
            ctx.setLineDash([]);
            
            // RSSI label at midpoint
            const mx = (gp.x + ep_px.x) / 2;
            const my = (gp.y + ep_px.y) / 2;
            const rssiText = `${rssi.toFixed(1)} dBm`;
            
            // Background box
            const tw = ctx.measureText(rssiText).width;
            ctx.fillStyle = 'rgba(0,0,0,0.8)';
            ctx.fillRect(mx - tw/2 - 3/zoom, my - 7/zoom, tw + 6/zoom, 14/zoom);
            
            // Color based on quality
            if (rssi > -65) ctx.fillStyle = '#00ff88';
            else if (rssi > -85) ctx.fillStyle = '#ffff00';
            else if (rssi > -120) ctx.fillStyle = '#ff8800';
            else ctx.fillStyle = '#ff4444';
            
            ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.fillText(rssiText, mx, my);
            ctx.textAlign = 'start'; ctx.textBaseline = 'alphabetic';
        }
    }
}

function drawMeasure() {
    const s = kmToPx(measureStart.x, measureStart.y);
    // Fixed screen-size dots: 3px regardless of zoom
    const dotR = 3 / zoom;
    ctx.fillStyle = '#00ff00';
    ctx.beginPath(); ctx.arc(s.x, s.y, dotR, 0, Math.PI*2); ctx.fill();
    if (measureEnd) {
        const e = kmToPx(measureEnd.x, measureEnd.y);
        ctx.strokeStyle = '#00ff00'; ctx.lineWidth = 1.5 / zoom; ctx.setLineDash([4/zoom, 4/zoom]);
        ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(e.x, e.y); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = '#ff4444';
        ctx.beginPath(); ctx.arc(e.x, e.y, dotR, 0, Math.PI*2); ctx.fill();
        const dx = measureEnd.x - measureStart.x, dy = measureEnd.y - measureStart.y;
        const distM = Math.sqrt(dx*dx+dy*dy)*1000;
        const mx = (s.x+e.x)/2, my = (s.y+e.y)/2;
        ctx.fillStyle = '#fff';
        ctx.font = `bold 12px monospace`;
        ctx.fillText(formatDistance(distM), mx + 5/zoom, my - 5/zoom);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Stats
// ═══════════════════════════════════════════════════════════════════════
function updateStats(stats) {
    if (!stats) {
        ['stat-coverage','stat-rssi','stat-snr','stat-points'].forEach(id => document.getElementById(id).textContent = '—');
        return;
    }
    document.getElementById('stat-coverage').textContent = stats.coverage_pct.toFixed(1) + '%';
    document.getElementById('stat-rssi').textContent = stats.mean_rssi_dbm.toFixed(1) + ' dBm';
    document.getElementById('stat-snr').textContent = stats.mean_snr_db.toFixed(1) + ' dB';
    document.getElementById('stat-points').textContent = stats.total_points;
}

function updatePerTechStats(pts) {
    const el = document.getElementById('per-tech-stats');
    if (!pts) { el.innerHTML = ''; return; }
    let html = '';
    const techNames = { halow: '🛜 HaLow', lorawan: '📡 LoRaWAN', nbiot: '📶 NB-IoT' };
    for (const tech of ['halow', 'lorawan', 'nbiot']) {
        const s = pts[tech];
        if (!s) continue;
        html += `<div style="margin-top:6px;font-size:11px;color:#888;font-weight:bold">${techNames[tech]}</div>`;
        html += `<div class="stat-row"><span class="stat-label">Coverage:</span><span class="stat-value">${s.coverage_pct.toFixed(1)}%</span></div>`;
        html += `<div class="stat-row"><span class="stat-label">Mean RSSI:</span><span class="stat-value">${s.mean_rssi_dbm.toFixed(1)} dBm</span></div>`;
        html += `<div class="stat-row"><span class="stat-label">Mean SNR:</span><span class="stat-value">${s.mean_snr_db.toFixed(1)} dB</span></div>`;
    }
    el.innerHTML = html;
}

function updateCounts() {
    // Invalidate heatmap cache when devices change (color palette depends on tech mix)
    heatmapCacheDirty = true;
    const counts = {
        halow_ap: 0, halow_endpoint: 0,
        lorawan_gateway: 0, lorawan_endpoint: 0,
        nbiot_base: 0, nbiot_endpoint: 0,
        power_meter: 0,
    };
    devices.forEach(d => { if (counts[d.type] !== undefined) counts[d.type]++; });

    const el = document.getElementById('device-stats');
    el.innerHTML = `
        <div class="stat-row"><span class="stat-label">HaLow Access Points:</span><span class="stat-value">${counts.halow_ap}</span></div>
        <div class="stat-row"><span class="stat-label">HaLow Endpoints:</span><span class="stat-value">${counts.halow_endpoint}</span></div>
        <div class="stat-row"><span class="stat-label">LoRaWAN Gateways:</span><span class="stat-value">${counts.lorawan_gateway}</span></div>
        <div class="stat-row"><span class="stat-label">LoRaWAN Endpoints:</span><span class="stat-value">${counts.lorawan_endpoint}</span></div>
        <div class="stat-row"><span class="stat-label">NB-IoT Cellular Modules:</span><span class="stat-value">${counts.nbiot_base}</span></div>
        <div class="stat-row"><span class="stat-label">NB-IoT Endpoints:</span><span class="stat-value">${counts.nbiot_endpoint}</span></div>
        <div class="stat-row"><span class="stat-label">Power Meters:</span><span class="stat-value">${counts.power_meter}</span></div>
        <div class="stat-row"><span class="stat-label">Obstacles:</span><span class="stat-value">${obstacles.length}</span></div>
    `;
}

// ═══════════════════════════════════════════════════════════════════════
// Leaflet Map Overlay
// ═══════════════════════════════════════════════════════════════════════
let mapEnabled = false;
let leafletMap = null;
let streetLayer = null;
let satelliteLayer = null;
let currentLayer = null;

const mapContainer = document.getElementById('map-container');
const mapControls = document.getElementById('map-controls');

function initLeafletMap() {
    if (leafletMap) return;
    leafletMap = L.map('map-container', {
        zoomControl: false,
        attributionControl: false,
        dragging: false,
        scrollWheelZoom: false,
        doubleClickZoom: false,
        boxZoom: false,
        keyboard: false,
        touchZoom: false,
    });
    streetLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 20 });
    satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 20 });
    currentLayer = streetLayer;
    currentLayer.addTo(leafletMap);
}

function syncMapToGrid() {
    if (!leafletMap) return;
    const lat = parseFloat(document.getElementById('map-lat').value) || 30.2672;
    const lng = parseFloat(document.getElementById('map-lng').value) || -97.7431;

    // Map fills entire scrollable area (same as canvas)
    const canvasW = parseFloat(canvas.style.width) || container.clientWidth;
    const canvasH = parseFloat(canvas.style.height) || container.clientHeight;
    mapContainer.style.width = canvasW + 'px';
    mapContainer.style.height = canvasH + 'px';
    mapContainer.style.left = canvas.style.marginLeft;
    mapContainer.style.top = canvas.style.marginTop;
    leafletMap.invalidateSize();

    // Always show 5km × 5km area centered on the requested lat/lng
    const mapSizeKm = 5;
    const halfW = mapSizeKm / 2;
    const halfH = mapSizeKm / 2;
    const latPerKm = 1 / 110.574;
    const lngPerKm = 1 / (111.320 * Math.cos(lat * Math.PI / 180));

    const south = lat - halfH * latPerKm;
    const north = lat + halfH * latPerKm;
    const west = lng - halfW * lngPerKm;
    const east = lng + halfW * lngPerKm;

    leafletMap.fitBounds([[south, west], [north, east]], { animate: false, padding: [0, 0] });
    // Store base zoom for proportional zooming
    setTimeout(() => {
        leafletMap.invalidateSize();
        leafletMap.fitBounds([[south, west], [north, east]], { animate: false, padding: [0, 0] });
        leafletMap._baseZoom = leafletMap.getZoom();
    }, 200);
}

document.getElementById('toggle-map').addEventListener('click', () => {
    mapEnabled = !mapEnabled;
    const btn = document.getElementById('toggle-map');
    if (mapEnabled) {
        btn.textContent = '🗺 Hide Map';
        btn.style.background = '#2e7d32';
        mapControls.style.display = 'flex';
        mapContainer.style.display = 'block';
        initLeafletMap();
        syncMapToGrid();
    } else {
        btn.textContent = '🗺 Map';
        btn.style.background = '';
        mapControls.style.display = 'none';
        mapContainer.style.display = 'none';
    }
    redraw();
});

document.getElementById('map-apply').addEventListener('click', () => {
    if (mapEnabled) syncMapToGrid();
});

document.getElementById('map-layer').addEventListener('change', e => {
    if (!leafletMap) return;
    if (currentLayer) leafletMap.removeLayer(currentLayer);
    currentLayer = e.target.value === 'satellite' ? satelliteLayer : streetLayer;
    currentLayer.addTo(leafletMap);
});

// Re-sync map when canvas resizes
const _origSetupCanvas = setupCanvas;
setupCanvas = function() {
    _origSetupCanvas();
    if (mapEnabled && leafletMap) syncMapToGrid();
};

// Grid opacity slider
document.getElementById('grid-opacity').addEventListener('input', e => {
    gridOpacity = parseInt(e.target.value) / 100;
    redraw();
});

// ═══════════════════════════════════════════════════════════════════════
// Display toggle checkboxes
// ═══════════════════════════════════════════════════════════════════════
function onToggleChange() {
    heatmapCacheDirty = true;
    if (simActive) runSimulation();
    else redraw();
}
document.getElementById('toggle-halow').addEventListener('change', e => { showHalow = e.target.checked; onToggleChange(); });
document.getElementById('toggle-lorawan').addEventListener('change', e => { showLorawan = e.target.checked; onToggleChange(); });
document.getElementById('toggle-nbiot').addEventListener('change', e => { showNbiot = e.target.checked; onToggleChange(); });
document.getElementById('toggle-interference').addEventListener('change', e => { showInterference = e.target.checked; onToggleChange(); });
document.getElementById('toggle-obstacles-att').addEventListener('change', e => { showObstacleAtt = e.target.checked; onToggleChange(); });
document.getElementById('toggle-shadow-fading').addEventListener('change', e => { shadowFading = e.target.checked; onToggleChange(); });
document.getElementById('toggle-multipath-fading').addEventListener('change', e => { multipathFading = e.target.checked; onToggleChange(); });
document.getElementById('env-type').addEventListener('change', () => { if (simActive) runSimulation(); });

// ═══════════════════════════════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════════════════════════════
window.addEventListener('resize', setupCanvas);
populateHalowChannels();
updateLoraDatarate();
updateCounts();
setupCanvas();
