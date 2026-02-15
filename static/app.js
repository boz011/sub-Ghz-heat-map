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
const MIN_ZOOM = 0.25, MAX_ZOOM = 4.0, ZOOM_STEP = 0.1;

let gridCfg = { width_km: 5, height_km: 5, resolution_m: 50 };

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

// Obstacle types that can be placed
const OBSTACLE_TYPES = ['wall','house','water','forest','water_tower'];

// ═══════════════════════════════════════════════════════════════════════
// Mouse state machine
// ═══════════════════════════════════════════════════════════════════════
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
function setupCanvas() {
    const dpr = window.devicePixelRatio || 1;
    const baseW = gridCfg.width_km * 120;
    const baseH = gridCfg.height_km * 120;
    const w = baseW * zoom;
    const h = baseH * zoom;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    redraw();
}

// ═══════════════════════════════════════════════════════════════════════
// Coordinate conversions — Y increases DOWNWARD (screen-style)
// Top-left = (0,0), bottom-right = (width_km, height_km)
// ═══════════════════════════════════════════════════════════════════════
function screenToKm(clientX, clientY) {
    const r = canvas.getBoundingClientRect();
    const px = clientX - r.left;
    const py = clientY - r.top;
    return { x: px / (120 * zoom), y: py / (120 * zoom) };
}
function screenToPx(clientX, clientY) {
    const r = canvas.getBoundingClientRect();
    return { x: clientX - r.left, y: clientY - r.top };
}
function kmToPx(xKm, yKm) {
    return { x: xKm * 120 * zoom, y: yKm * 120 * zoom };
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
document.getElementById('grid-width').addEventListener('change', e => { gridCfg.width_km = parseInt(e.target.value)||5; setupCanvas(); });
document.getElementById('grid-height').addEventListener('change', e => { gridCfg.height_km = parseInt(e.target.value)||5; setupCanvas(); });
document.getElementById('resolution').addEventListener('change', e => { gridCfg.resolution_m = parseFloat(e.target.value)||50; });

container.addEventListener('wheel', e => {
    e.preventDefault();
    zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom + (e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP)));
    document.getElementById('zoom-level').textContent = Math.round(zoom*100)+'%';
    setupCanvas();
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
        const w = o.width_km * 120 * zoom, h = o.height_km * 120 * zoom;
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
        const snapThreshKm = 15 / (120 * zoom);
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
        obsDrawStart = km;
        tempObs = {
            id: nextId(selectedType),
            type: selectedType,
            position: { x: km.x, y: km.y },
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
        redraw();
        return;
    }

    if (mouseState === 'resizing' && resizeTarget) {
        resizeTarget.width_km = Math.max(0.05, km.x - resizeTarget.position.x);
        resizeTarget.height_km = Math.max(0.05, km.y - resizeTarget.position.y);
        redraw();
        return;
    }

    if (mouseState === 'drawing-obs' && tempObs && obsDrawStart) {
        tempObs.position.x = Math.min(obsDrawStart.x, km.x);
        tempObs.position.y = Math.min(obsDrawStart.y, km.y);
        tempObs.width_km = Math.abs(km.x - obsDrawStart.x);
        tempObs.height_km = Math.abs(km.y - obsDrawStart.y);
        redraw();
        return;
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
    }

    if (mouseState === 'drawing-obs' && tempObs) {
        if (tempObs.width_km > 0.03 && tempObs.height_km > 0.03) {
            obstacles.push(tempObs);
            updateCounts();
            statusEl.textContent = `Placed ${tempObs.type} — drag to draw more, Esc to deselect`;
        }
        tempObs = null; obsDrawStart = null;
        redraw();
    }

    if (mouseState === 'dragging') {
        if (dragTarget) delete dragTarget._dragOff;
        statusEl.textContent = 'Moved';
    }
    if (mouseState === 'resizing') statusEl.textContent = 'Resized';

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
        return;
    }

    // Check obstacle
    const obs = obstacleAtScreen(cx, cy);
    if (obs) {
        obstacles = obstacles.filter(o => o !== obs);
        updateCounts();
        statusEl.textContent = `Removed ${obs.type}`;
        redraw();
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
    if (devices.length === 0) { statusEl.textContent = 'Place devices first!'; return; }
    statusEl.textContent = 'Running simulation...';
    try {
        const resp = await fetch('/api/simulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                width_km: gridCfg.width_km,
                height_km: gridCfg.height_km,
                resolution_m: gridCfg.resolution_m,
                devices: devices,
                obstacles: obstacles,
            }),
        });
        const data = await resp.json();
        if (data.ok) {
            heatmapData = data.result;
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
        updateStats(null);
        updatePerTechStats(null);
        redraw();
        statusEl.textContent = 'Simulation off';
    }
});

document.getElementById('clear-all').addEventListener('click', () => {
    if (!confirm('Clear everything?')) return;
    devices = []; obstacles = []; heatmapData = null;
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
    ctx.strokeStyle = '#333'; ctx.lineWidth = 0.5;
    // X-axis labels (left to right)
    for (let km = 0; km <= gridCfg.width_km; km++) {
        const x = km * 120 * zoom;
        ctx.beginPath(); ctx.moveTo(x, 0);
        ctx.lineTo(x, gridCfg.height_km * 120 * zoom); ctx.stroke();
        ctx.fillStyle = '#555'; ctx.font = `${Math.max(9, 10*zoom)}px monospace`;
        ctx.fillText(km + 'km', x + 2, 12*zoom);
    }
    // Y-axis labels — 0km at top, increasing downward
    for (let km = 0; km <= gridCfg.height_km; km++) {
        const y = km * 120 * zoom;
        ctx.beginPath(); ctx.moveTo(0, y);
        ctx.lineTo(gridCfg.width_km * 120 * zoom, y); ctx.stroke();
        ctx.fillStyle = '#555'; ctx.font = `${Math.max(9, 10*zoom)}px monospace`;
        ctx.fillText(km + 'km', 2, y - 3);
    }
}

function drawHeatmap() {
    const { rssi_grid, interference_grid, grid_shape } = heatmapData;
    const [rows, cols] = grid_shape;
    const cw = (gridCfg.width_km * 120 * zoom) / cols;
    const ch = (gridCfg.height_km * 120 * zoom) / rows;
    // Grid row 0 = top of map (Y=0), row N = bottom (Y=height_km)
    for (let i = 0; i < rows; i++) {
        for (let j = 0; j < cols; j++) {
            const rssi = rssi_grid[i][j];
            ctx.fillStyle = rssiColor(rssi);
            ctx.fillRect(j * cw, i * ch, cw, ch);
        }
    }
    // Draw interference overlay in dark orange
    if (interference_grid) {
        for (let i = 0; i < rows; i++) {
            for (let j = 0; j < cols; j++) {
                const interf = interference_grid[i][j];
                if (interf > -120) {
                    // Stronger interference = more opaque
                    const alpha = Math.min(0.6, Math.max(0.05, (interf + 120) / 80));
                    ctx.fillStyle = `rgba(0,0,160,${alpha.toFixed(2)})`;
                    ctx.fillRect(j * cw, i * ch, cw, ch);
                }
            }
        }
    }
}

function rssiColor(rssi) {
    const a = mapEnabled ? 0.25 : 0.45;
    const a2 = mapEnabled ? 0.2 : 0.4;
    const a3 = mapEnabled ? 0.15 : 0.35;
    const a4 = mapEnabled ? 0.1 : 0.3;
    if (rssi > -65) return `rgba(0,255,0,${a})`;
    if (rssi > -85) return `rgba(136,255,0,${a2})`;
    if (rssi > -100) return `rgba(255,255,0,${a3})`;
    if (rssi > -120) return `rgba(255,136,0,${a4})`;
    return `rgba(255,0,0,${mapEnabled ? 0.08 : 0.2})`;
}

function drawObstacles() { obstacles.forEach(o => drawOneObs(o, false)); }
function drawOneObs(o, isTemp) {
    // Y-down: position is top-left corner
    const tl = kmToPx(o.position.x, o.position.y);
    const w = o.width_km * 120 * zoom, h = o.height_km * 120 * zoom;
    ctx.globalAlpha = isTemp ? 0.5 : 0.7;
    ctx.fillStyle = OBS_COLORS[o.type] || '#888';
    ctx.fillRect(tl.x, tl.y, w, h);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5;
    ctx.strokeRect(tl.x, tl.y, w, h);
    ctx.fillStyle = '#fff'; ctx.font = `${Math.max(9, 10*zoom)}px sans-serif`;
    const typeNames = { wall:'Wall', house:'House', water:'Water Pond', forest:'Forest', water_tower:'Water Tower' };
    const lbl = (typeNames[o.type] || o.type) + (o.type === 'wall' ? ' (' + o.material + ')' : '');
    ctx.fillText(lbl, tl.x + 4, tl.y + 13*zoom);
    if (!isTemp) {
        // Resize handle at bottom-right
        ctx.fillStyle = '#0088ff';
        ctx.fillRect(tl.x + w - 7, tl.y + h - 7, 7, 7);
    }
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
            ctx.beginPath(); ctx.arc(p.x, p.y, r * 120 * zoom, 0, Math.PI*2); ctx.stroke();
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
}

function drawMeasure() {
    const s = kmToPx(measureStart.x, measureStart.y);
    ctx.fillStyle = '#00ff00';
    ctx.beginPath(); ctx.arc(s.x, s.y, 4*zoom, 0, Math.PI*2); ctx.fill();
    if (measureEnd) {
        const e = kmToPx(measureEnd.x, measureEnd.y);
        ctx.strokeStyle = '#00ff00'; ctx.lineWidth = 2; ctx.setLineDash([5,5]);
        ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(e.x, e.y); ctx.stroke();
        ctx.setLineDash([]);
        ctx.beginPath(); ctx.arc(e.x, e.y, 4*zoom, 0, Math.PI*2); ctx.fill();
        const dx = measureEnd.x - measureStart.x, dy = measureEnd.y - measureStart.y;
        const distM = Math.sqrt(dx*dx+dy*dy)*1000;
        const mx = (s.x+e.x)/2, my = (s.y+e.y)/2;
        ctx.font = `bold ${12*zoom}px monospace`;
        ctx.fillText(formatDistance(distM), mx+5, my-5);
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
    streetLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 });
    satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19 });
    currentLayer = streetLayer;
    currentLayer.addTo(leafletMap);
}

function syncMapToGrid() {
    if (!leafletMap) return;
    const lat = parseFloat(document.getElementById('map-lat').value) || 30.2672;
    const lng = parseFloat(document.getElementById('map-lng').value) || -97.7431;

    const w = parseFloat(canvas.style.width);
    const h = parseFloat(canvas.style.height);
    mapContainer.style.width = w + 'px';
    mapContainer.style.height = h + 'px';
    leafletMap.invalidateSize();

    const halfW = gridCfg.width_km / 2;
    const halfH = gridCfg.height_km / 2;
    const latPerKm = 1 / 111.0;
    const lngPerKm = 1 / (111.0 * Math.cos(lat * Math.PI / 180));

    const south = lat - halfH * latPerKm;
    const north = lat + halfH * latPerKm;
    const west = lng - halfW * lngPerKm;
    const east = lng + halfW * lngPerKm;

    leafletMap.fitBounds([[south, west], [north, east]]);
    setTimeout(() => leafletMap.invalidateSize(), 100);
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

// ═══════════════════════════════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════════════════════════════
window.addEventListener('resize', setupCanvas);
populateHalowChannels();
updateLoraDatarate();
updateCounts();
setupCanvas();
