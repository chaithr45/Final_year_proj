/* SeizeLUT live dashboard: listens to the board's event stream (/api/stream) and draws every stage. No libraries. */
'use strict';
const $ = (id) => document.getElementById(id);
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const DPR = () => Math.min(2, window.devicePixelRatio || 1);
const VIEW_S = 10;                         // seconds of signal on screen

const S = {
  info: null, seg: null, phase: 'idle', playing: false, speed: 1, op: 'strict', pos: 0,
  timeline: [], events: [], opMarks: [], chunks: {}, scales: {}, beats: [],
  recvEnd: 0, dispEnd: 0, last: null, alarm: 0, nAlarm: 0, sound: true, audio: null,
  io: 0, boardLeds: null, rtt: null, lat: 3, nwinHw: 0, connected: false, virt: { flash: 0 },
  onsetToasted: {}, colors: {},
};

const STRIPS = [
  { name: 'EEG 1', sub: 'behind the ear', raw: 'eeg1', filt: 'eeg1_f', color: '--eeg1', fs: 256, need: 'eeg1' },
  { name: 'EEG 2', sub: 'across the head', raw: 'eeg2', filt: 'eeg2_f', color: '--eeg2', fs: 256, need: 'eeg2' },
  { name: 'ECG', sub: 'heart', raw: 'ecg', filt: 'ecg_f', color: '--ecg', fs: 256, beats: true, need: 'ecg' },
  { name: 'EMG', sub: 'muscle', raw: null, filt: 'emg_f', color: '--emg', fs: 256, need: 'emg' },
  { name: 'Motion', sub: 'accelerometer', raw: null, filt: 'acc_m', alt: 'gyr_m', color: '--mov', fs: 25, motion: true, need: 'acc_x' },
];

const FEAT_LABEL = {
  eeg_theta_mean: 'EEG θ power', ecg_log_rr: 'ECG RR interval', eeg_ch2_theta: 'EEG2 θ power', eeg_theta_max: 'EEG θ max',
  eeg_beta_mean_ctx: 'EEG β vs last min', ecg_log_rr_ctx: 'RR vs last min', eeg_hf_mean_ctx: 'EEG HF vs last min',
  ecg_log_masrd: 'ECG heart-rate var.', eeg_mav_absdiff: 'EEG amp. L−R diff', eeg_hf_max_ctx: 'EEG HF max vs min',
  emg_mav: 'EMG amplitude', mov_acc_jerk: 'ACC jerk', eeg_sign_agree: 'EEG ch. agreement', mov_acc_mag: 'ACC magnitude',
  eeg_theta_max_ctx: 'EEG θ max vs min', eeg_theta_mean_ctx: 'EEG θ vs last min', eeg_ll_absdiff: 'EEG line-len diff',
  ecg_quality_bad: 'ECG quality flag', emg_ll: 'EMG line length', eeg_delta_mean: 'EEG δ power', eeg_ch2_hf: 'EEG2 HF power',
  emg_zc: 'EMG zero crossings', eeg_ch1_hf: 'EEG1 HF power', mov_gyr_mag: 'GYR magnitude', eeg_theta_absdiff: 'EEG θ L−R diff',
  eeg_ch2_mav: 'EEG2 amplitude', eeg_alpha_mean_ctx: 'EEG α vs last min', mov_acc_jerk_ctx: 'ACC jerk vs min',
  eeg_ext_absdiff: 'EEG extrema diff', ecg_log_masrd_ctx: 'HRV vs last min', eeg_mob_mean_ctx: 'EEG mobility vs min',
  mov_gyr_jerk: 'GYR jerk', eeg_delta_max: 'EEG δ max', eeg_delta_absdiff: 'EEG δ L−R diff', mov_gyr_act_ctx: 'GYR activity vs min',
  eeg_ch2_alpha: 'EEG2 α power', eeg_hf_absdiff_ctx: 'EEG HF diff vs min', eeg_ch1_theta: 'EEG1 θ power',
};
const OP_LABEL = { strict: 'Strict', balanced: 'Balanced', sensitive: 'Sensitive' };
const OP_TIP = {
  strict: 'Frozen in the chip: fewest false alarms (decision threshold 9, 10 of 10 windows)',
  balanced: 'Chosen on the training patients for at most about 1 false alarm per hour (threshold 2)',
  sensitive: 'Catches more seizures, more false alarms (threshold −7; stage 1 of the post-ictal cascade)',
};

// ------------------------------------------------------------------ helpers
function fmtHMS(s) {
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}`;
}
function fmtMS(s) {
  const neg = s < 0; s = Math.abs(Math.round(s));
  return `${neg ? '−' : ''}${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
function post(cmd, extra = {}) {
  return fetch('/api/cmd', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cmd, ...extra }) }).catch(() => {});
}
function toast(msg, kind = '') {
  const t = document.createElement('div');
  t.className = 'toast ' + kind; t.innerHTML = msg;
  $('toasts').appendChild(t);
  setTimeout(() => { t.style.transition = 'opacity .5s'; t.style.opacity = '0'; }, 5200);
  setTimeout(() => t.remove(), 5800);
  while ($('toasts').children.length > 3) $('toasts').firstChild.remove();
}
function sizeCanvas(c) {
  const r = c.getBoundingClientRect(), d = DPR();
  const w = Math.max(10, Math.round(r.width * d)), h = Math.max(10, Math.round(r.height * d));
  if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
  return { w, h, d };
}
function featClass(n) { return n.startsWith('ecg') ? 'ecg' : n.startsWith('emg') ? 'emg' : n.startsWith('mov') ? 'mov' : 'eeg'; }
function segSensors(seg) { return new Set(seg ? seg.sensors : []); }
function inSeizure(t) { return S.seg && S.seg.seizures_s.some(([a, b]) => t >= a && t < b); }

// ------------------------------------------------------------------ static UI
function buildFeatures() {
  const box = $('feats'); box.innerHTML = '';
  const F = S.info.features;
  S.featEls = new Array(F.length);
  F.forEach((f, i) => {
    const lo0 = Math.min(...f.thr), hi0 = Math.max(...f.thr);
    const pad = Math.max(6, (hi0 - lo0) * 0.35);
    f.lo = lo0 - pad; f.hi = hi0 + pad;
    const row = document.createElement('div');
    row.className = 'feat ' + featClass(f.name);
    row.title = `${FEAT_LABEL[f.name] || f.name} (${f.name}): ${f.thr.length} comparator(s) at ${f.thr.join(', ')}`;
    row.innerHTML = `<span class="fl">${FEAT_LABEL[f.name] || f.name}</span><span class="ft"><span class="ff"></span></span>`;
    const tr = row.querySelector('.ft');
    const ticks = f.thr.map((t) => {
      const k = document.createElement('i'); k.className = 'tk';
      k.style.left = (100 * (t - f.lo) / (f.hi - f.lo)) + '%'; tr.appendChild(k); return k;
    });
    S.featEls[i] = { fill: row.querySelector('.ff'), ticks };
    box.appendChild(row);
  });
  layoutFeatures();
}
function layoutFeatures() {
  // as many rows as fit at about 12.5 px each; the columns follow (2 on a large screen, 3-4 on a small one)
  const box = $('feats'), n = S.info.features.length;
  const h = box.clientHeight || 200, w = box.clientWidth || 400;
  const rows = clamp(Math.floor(h / 12.5), 8, Math.ceil(n / 2));
  const cols = Math.ceil(n / rows);
  box.style.gridTemplateRows = `repeat(${rows}, minmax(0, 1fr))`;
  box.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
  const colw = (w - 14 * (cols - 1)) / cols;
  box.style.setProperty('--fl', `${Math.round(clamp(colw * 0.5, 0, 118))}px`);
  box.style.setProperty('--fs', `${clamp(h / rows * 0.8, 8.5, 10.5).toFixed(1)}px`);
}
function buildLuts() {
  for (const [id, cls] of [['lutSz', 'szr'], ['lutBg', 'bgr']]) {
    const el = $(id); el.innerHTML = ''; el.classList.add(cls);
    for (let i = 0; i < 25; i++) { const c = document.createElement('i'); c.className = 'lut'; el.appendChild(c); }
  }
  const h = $('hist'); h.innerHTML = '';
  for (let i = 0; i < 10; i++) { const c = document.createElement('i'); c.className = 'hcell'; h.appendChild(c); }
  const r = document.createElement('span'); r.className = 'hres'; r.id = 'hres'; r.textContent = 'no alarm'; h.appendChild(r);
}
function buildControls() {
  const sp = $('speeds'); sp.innerHTML = '';
  for (const v of [1, 2, 5, 10, 30]) {
    const b = document.createElement('button'); b.textContent = v + '×'; b.dataset.v = v;
    b.title = v === 1 ? 'Real time' : `${v} seconds of signal per second`;
    b.onclick = () => post('speed', { value: v }); sp.appendChild(b);
  }
  const op = $('ops'); op.innerHTML = '';
  for (const k of ['strict', 'balanced', 'sensitive']) {
    const b = document.createElement('button'); b.textContent = OP_LABEL[k]; b.dataset.v = k; b.className = k;
    b.title = OP_TIP[k]; b.onclick = () => post('op', { value: k }); op.appendChild(b);
  }
  $('bPlay').onclick = () => { unlockAudio(); post(S.playing ? 'pause' : 'play'); };
  $('bSkip').onclick = () => post('skip', { before: 30 });
  $('bRestart').onclick = () => { unlockAudio(); post('restart').then(() => post('play')); };
  $('bButton').onclick = () => { post('button', { source: 'screen' }); };
  $('bLed').onclick = () => post('ledtest');
  $('bSound').onclick = () => { unlockAudio(); S.sound = !S.sound; $('bSound').textContent = S.sound ? '🔊 Sound on' : '🔇 Sound off'; };
  $('bChoose').onclick = () => showChooser(true);
  $('bCloseChooser').onclick = () => showChooser(false);
  $('bReplay').onclick = () => { $('endBox').classList.remove('show'); post('restart').then(() => post('play')); };
  $('bOther').onclick = () => { $('endBox').classList.remove('show'); showChooser(true); };
  window.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    if (e.code === 'Space') { e.preventDefault(); $('bPlay').click(); }
    else if (e.key === 's' || e.key === 'S') $('bSkip').click();
    else if (e.key === 'b' || e.key === 'B') $('bButton').click();
    else if (e.key === 'l' || e.key === 'L') $('bLed').click();
    else if (e.key === 'i' || e.key === 'I') showChooser(true);
    else if (e.key === 'Escape') showChooser(false);
    else if ('12345'.includes(e.key)) post('speed', { value: [1, 2, 5, 10, 30][+e.key - 1] });
  });
}
function buildChooser() {
  const box = $('cards'); box.innerHTML = '';
  for (const s of S.info.segments) {
    const c = document.createElement('button'); c.className = 'card';
    const sens = new Set(s.sensors);
    const badges = ['<span class="badge eeg">EEG ×2</span>'];
    if (sens.has('ecg')) badges.push('<span class="badge ecg">ECG</span>');
    if (sens.has('emg')) badges.push('<span class="badge emg">EMG</span>');
    if (sens.has('acc_x')) badges.push('<span class="badge mov">accelerometer</span>');
    if (sens.has('gyr_x')) badges.push('<span class="badge mov">gyroscope</span>');
    badges.push(s.seizure_duration_s ? `<span class="badge sz">seizure ${Math.round(s.seizure_duration_s)} s</span>`
      : '<span class="badge none">no seizure</span>');
    const watch = s.seconds - s.watch_from_s;
    c.innerHTML = `<h3>${s.title}</h3><p>${s.story}</p><div class="badges">${badges.join('')}
      <span class="badge">${Math.round(watch / 60)} min to watch</span></div>`;
    c.onclick = () => { unlockAudio(); showChooser(false); post('load', { id: s.id }).then(() => post('play')); };
    box.appendChild(c);
  }
}
function showChooser(on) { $('chooser').classList.toggle('show', on); }

// ------------------------------------------------------------------ board drawing (SVG)
const PMOD_COLORS = ['#3ee68f', '#3ee68f', '#ffd23f', '#ffa63f', '#ff3049', '#222', '#4fa8ff'];
const PMOD_NAMES = ['A1 score low', 'A2 score mid', 'A3 score high', 'A4 decision', 'B1 ALARM', 'B2 buzzer', 'B3 heartbeat'];
function buildBoard() {
  const svg = $('boardSvg'), demo2 = S.info.demo === 2;
  const pins = []; for (let i = 0; i < 6; i++) pins.push(`<rect x="${197 + (i % 2) * 0}" y="0" width="0" height="0"/>`);
  let pm = '';
  for (let r = 0; r < 2; r++) for (let c = 0; c < 6; c++)
    pm += `<rect x="${200 + r * 7}" y="${38 + c * 7}" width="5" height="5" rx="1" fill="#c9a24a"/>`;
  let bb = '';
  const bx = 232, opacity = demo2 ? 1 : 0.28;
  bb += `<g opacity="${opacity}"><rect x="${bx}" y="14" width="62" height="146" rx="5" fill="#e9edf3" stroke="#9aa4b5"/>`;
  for (let i = 0; i < 7; i++) {
    const y = 26 + i * 18;
    const col = PMOD_COLORS[i];
    if (i === 5) bb += `<circle cx="${bx + 40}" cy="${y}" r="7" fill="#1a1a1a" stroke="#555"/><circle id="pm${i}" class="led" cx="${bx + 40}" cy="${y}" r="3" fill="#333"/>`;
    else bb += `<circle id="pm${i}" class="led" cx="${bx + 40}" cy="${y}" r="5.5" fill="#2a3040" stroke="${col}" stroke-width="1.2"/>`;
    bb += `<path class="wire" stroke="${col === '#222' ? '#888' : col}" d="M${207} ${41 + Math.min(i, 3) * 7 + (i > 3 ? (i - 4) * 7 : 0)} C 222 ${41 + i * 6}, 222 ${y}, ${bx + 32} ${y}"/>`;
    bb += `<text x="${bx + 49}" y="${y + 3}" font-size="6.5" fill="#333">${['A1', 'A2', 'A3', 'A4', 'B1', 'B2', 'B3'][i]}</text>`;
  }
  bb += `<rect x="${bx + 33}" y="${26 + 7 * 18 - 4}" width="14" height="10" rx="2" fill="#333" id="pmBtn"/><text x="${bx + 49}" y="${26 + 7 * 18 + 3}" font-size="6.5" fill="#333">B4</text>`;
  bb += demo2 ? '' : `<text x="${bx + 31}" y="90" font-size="8.5" fill="#000" text-anchor="middle" transform="rotate(-90 ${bx + 31} 90)">Demo 2: LEDs + buzzer</text>`;
  bb += '</g>';
  svg.innerHTML = `
  <defs><filter id="glow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="2.4" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <linearGradient id="hs" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#2a3446"/><stop offset="1" stop-color="#171d29"/></linearGradient></defs>
  <rect x="6" y="10" width="200" height="150" rx="8" fill="#0d1119" stroke="#2a3858"/>
  <text x="14" y="23" font-size="8" fill="#56627f">KV260 carrier card</text>
  <rect x="48" y="28" width="128" height="88" rx="5" fill="url(#hs)" stroke="#3a4560"/>
  ${Array.from({ length: 11 }, (_, i) => `<line x1="${54 + i * 11}" y1="32" x2="${54 + i * 11}" y2="112" stroke="#222b3b" stroke-width="2"/>`).join('')}
  <circle cx="112" cy="72" r="31" fill="#0b0f16" stroke="#3a4560"/>
  <g class="fan" id="fan">${Array.from({ length: 7 }, (_, i) => `<path d="M112 72 q 8 -24 26 -18 q -12 6 -26 18z" fill="#2c3648" transform="rotate(${i * 51.4} 112 72)"/>`).join('')}
    <circle cx="112" cy="72" r="6" fill="#3a4560"/></g>
  <text x="112" y="125" font-size="7.5" fill="#8d9aba" text-anchor="middle">K26 SOM · Zynq UltraScale+ (ARM + FPGA)</text>
  <circle id="ds35" class="led" cx="40" cy="132" r="4.5" fill="#1b2233" stroke="#3a4560"/>
  <circle id="ds36" class="led" cx="40" cy="146" r="4.5" fill="#1b2233" stroke="#3a4560"/>
  <text x="49" y="135" font-size="7" fill="#8d9aba">DS35 heartbeat</text><text x="49" y="149" font-size="7" fill="#8d9aba">DS36 decision / alarm</text>
  <rect x="196" y="34" width="16" height="46" rx="2" fill="#151a24" stroke="#4a5570"/>${pm}
  <text x="204" y="92" font-size="7" fill="#8d9aba" text-anchor="middle">PMOD</text>
  <rect x="150" y="136" width="26" height="18" rx="2" fill="#2a3040" stroke="#4a5570"/><text x="163" y="148" font-size="6.5" fill="#8d9aba" text-anchor="middle">ETH</text>
  <path d="M176 145 C 196 145, 200 165, 230 165" stroke="#4fd8ff" stroke-dasharray="3 3" fill="none" opacity=".7"><animate attributeName="stroke-dashoffset" from="12" to="0" dur=".6s" repeatCount="indefinite"/></path>
  <text x="125" y="166" font-size="6.5" fill="#4fd8ff">to laptop</text>
  ${bb}`;
  $('boardSub').textContent = demo2 ? 'Demo 2 · PMOD LEDs, buzzer and button connected' :
    (S.info.board_leds_on ? 'Demo 1 · the board\'s own LEDs DS35 / DS36' : 'board LEDs shown here');
}
function setLed(id, on, color) {
  const e = document.getElementById(id); if (!e) return;
  e.setAttribute('fill', on ? color : (id.startsWith('pm') ? (id === 'pm5' ? '#333' : '#2a3040') : '#1b2233'));
  if (on) e.setAttribute('filter', 'url(#glow)'); else e.removeAttribute('filter');
}
function renderLeds(now) {
  for (let i = 0; i < 7; i++) setLed('pm' + i, (S.io >> i) & 1, i === 5 ? '#ff3049' : PMOD_COLORS[i]);
  let ds;
  if (S.boardLeds && S.boardLeds.length) ds = S.boardLeds;
  else {   // same pattern as board_io.py, drawn from the window results
    const hb = S.alarm ? (Math.floor(now / 100) % 2 === 0) : now < S.virt.flash;
    ds = [hb ? 1 : 0, (S.last && (S.last.dec || S.last.alarm)) ? 1 : 0];
  }
  setLed('ds35', ds[0], '#7dff9a'); setLed('ds36', ds[1], S.alarm ? '#ff4060' : '#ffc94a');
}

// ------------------------------------------------------------------ data path ribbon (canvas)
const NODES = [
  { t: 'Sensors', g: 0 }, { t: 'Front end', g: 1 }, { t: '38 features', g: 1 }, { t: '146 comparators', g: 2 },
  { t: '50 LUT6', g: 2 }, { t: 'Score', g: 2 }, { t: 'k-of-10 alarm', g: 2 }, { t: 'Alarm out', g: 3 },
];
const P = { packets: [], glow: new Array(NODES.length).fill(0) };
function nodeSub(i) {
  const L = S.last, sens = segSensors(S.seg);
  switch (i) {
    case 0: return S.seg ? ['EEG×2', sens.has('ecg') && 'ECG', sens.has('emg') && 'EMG', sens.has('acc_x') && 'ACC', sens.has('gyr_x') && 'GYR'].filter(Boolean).join(' · ') : '';
    case 1: return 'integer IIR filters · R-peaks';
    case 2: return L ? `window ${fmtMS(L.t_end - 2 - S.seg.watch_from_s)}–${fmtMS(L.t_end - S.seg.watch_from_s)}` : '2-s window, 1-s hop';
    case 3: return L ? `${countOnes(L.bits)} of 146 = 1` : 'feature > threshold';
    case 4: return L ? `${countOnes(L.luts.slice(25))} seizure · ${countOnes(L.luts.slice(0, 25))} background` : '6-input truth tables';
    case 5: return L ? `${L.score >= 0 ? '+' : ''}${L.score}  (≥ ${L.thr}? ${L.score >= L.thr ? 'yes' : 'no'})` : 'popcount difference';
    case 6: return L ? `${L.hist ? L.hist.reduce((a, b) => a + b, 0) : 0} of last 10 · need ${L.k}` : `${S.info ? S.info.k : 10} of last 10`;
    case 7: return S.alarm ? 'ALARM' : 'LEDs · buzzer · screen';
  }
  return '';
}
function countOnes(s) { let n = 0; for (const ch of s) n += ch === '1'; return n; }
function spawnPackets(win) {
  const now = performance.now();
  const hop = clamp(900 / S.speed / 8, 60, 260);
  P.packets.push({ a: 0, b: 1, t0: now, dur: hop * 1.4, col: '#4fd8ff' });
  if (!win) return;
  const col = win.alarm ? '#ff3049' : win.dec ? '#ffb21f' : '#6fa8ff';
  for (let i = 1; i < NODES.length - 1; i++)
    P.packets.push({ a: i, b: i + 1, t0: now + hop * (i - 1) * 0.8, dur: hop, col });
}
function drawPipe(now) {
  const c = $('pipe'), { w, h, d } = sizeCanvas(c), g = c.getContext('2d');
  g.clearRect(0, 0, w, h);
  const n = NODES.length, padX = 14 * d, gap = 18 * d;
  const nw = (w - 2 * padX - gap * (n - 1)) / n, nh = 46 * d, y0 = h - nh - 10 * d;
  const X = (i) => padX + i * (nw + gap);
  // groups
  const fpgaLabel = S.info && S.info.backend === 'fpga' ? 'FPGA fabric · 100 MHz · 3 clock cycles per window'
    : 'FPGA core (emulated in software for this run)';
  const cpuLabel = S.info && S.info.platform.includes('no board') ? 'CPU of this computer · C code' : 'ARM Cortex-A53 · C code';
  const groups = [[1, 2, cpuLabel, '#4fd8ff'], [3, 6, fpgaLabel, '#ff8a3d']];
  for (const [a, b, lab, col] of groups) {
    const x = X(a) - 7 * d, x2 = X(b) + nw + 7 * d;
    g.strokeStyle = col + '88'; g.setLineDash([5 * d, 4 * d]); g.lineWidth = 1.2 * d;
    roundRect(g, x, y0 - 22 * d, x2 - x, nh + 30 * d, 9 * d); g.stroke(); g.setLineDash([]);
    g.fillStyle = col; g.font = `${600} ${11 * d}px system-ui, sans-serif`; g.fillText(lab, x + 8 * d, y0 - 9 * d);
  }
  // links
  for (let i = 0; i < n - 1; i++) {
    g.strokeStyle = '#2a3858'; g.lineWidth = 2 * d;
    g.beginPath(); g.moveTo(X(i) + nw, y0 + nh / 2); g.lineTo(X(i + 1), y0 + nh / 2); g.stroke();
  }
  // nodes
  for (let i = 0; i < n; i++) {
    P.glow[i] *= 0.92;
    const x = X(i), gl = P.glow[i];
    const alarmNode = i === n - 1 && S.alarm;
    g.fillStyle = alarmNode ? '#5a0f1c' : '#0b1222';
    g.strokeStyle = alarmNode ? '#ff3049' : `rgba(79,216,255,${0.25 + 0.75 * gl})`;
    g.lineWidth = (1 + 1.5 * gl) * d;
    if (gl > 0.05 || alarmNode) { g.shadowColor = alarmNode ? '#ff3049' : '#4fd8ff'; g.shadowBlur = (alarmNode ? 18 : 14 * gl) * d; }
    roundRect(g, x, y0, nw, nh, 8 * d); g.fill(); g.stroke(); g.shadowBlur = 0;
    g.fillStyle = '#e8eeff'; g.font = `600 ${12 * d}px system-ui, sans-serif`;
    fitText(g, NODES[i].t, x + 9 * d, y0 + 18 * d, nw - 14 * d);
    g.fillStyle = alarmNode ? '#ffd0d6' : '#8d9aba'; g.font = `${10.5 * d}px system-ui, sans-serif`;
    fitText(g, nodeSub(i), x + 9 * d, y0 + 35 * d, nw - 14 * d);
  }
  // packets
  P.packets = P.packets.filter((p) => now < p.t0 + p.dur + 30);
  for (const p of P.packets) {
    const u = (now - p.t0) / p.dur; if (u < 0 || u > 1) continue;
    const xa = X(p.a) + nw, xb = X(p.b), x = xa + (xb - xa) * u, y = y0 + nh / 2;
    if (u > 0.92) P.glow[p.b] = 1;
    g.fillStyle = p.col; g.shadowColor = p.col; g.shadowBlur = 12 * d;
    g.beginPath(); g.arc(x, y, 4 * d, 0, Math.PI * 2); g.fill(); g.shadowBlur = 0;
  }
}
function roundRect(g, x, y, w, h, r) {
  g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}
function fitText(g, s, x, y, maxw) {
  if (g.measureText(s).width <= maxw) { g.fillText(s, x, y); return; }
  while (s.length > 1 && g.measureText(s + '…').width > maxw) s = s.slice(0, -1);
  g.fillText(s + '…', x, y);
}

// ------------------------------------------------------------------ signals (canvas)
function pushChunk(key, b, arr) {
  if (!S.chunks[key]) S.chunks[key] = new Map();
  S.chunks[key].set(b, arr);
  for (const k of S.chunks[key].keys()) if (k < b - VIEW_S - 4) S.chunks[key].delete(k);
  // robust amplitude of this second: 98th percentile of |x - mean|
  let m = 0; for (const v of arr) m += v; m /= arr.length;
  if (key === 'acc_m' || key === 'gyr_m') m = 0;          // magnitudes: scale from zero
  const dev = arr.map((v) => Math.abs(v - m)).sort((a, b2) => a - b2);
  const a = dev[Math.floor(dev.length * 0.98)] || 1;
  if (!S.scales[key]) S.scales[key] = { per: new Map(), cur: a };
  S.scales[key].per.set(b, a);
  for (const k of S.scales[key].per.keys()) if (k < b - VIEW_S) S.scales[key].per.delete(k);
}
function stripScale(key) {
  const s = S.scales[key]; if (!s) return 1;
  let mx = 1; for (const v of s.per.values()) mx = Math.max(mx, v);
  s.cur += (mx - s.cur) * 0.08;
  return s.cur;
}
function drawSignals() {
  const c = $('sig'), { w, h, d } = sizeCanvas(c), g = c.getContext('2d');
  g.clearRect(0, 0, w, h);
  const labW = 118 * d, axisH = 18 * d, x0 = labW, pw = w - labW - 10 * d, ph = h - axisH - 4 * d;
  const sens = segSensors(S.seg), n = STRIPS.length, sh = ph / n;
  const end = S.dispEnd, start = end - VIEW_S;
  const X = (t) => x0 + (t - start) / VIEW_S * pw;
  // seizure annotation bands
  if (S.seg) for (const [a, b] of S.seg.seizures_s) {
    const xa = clamp(X(a), x0, x0 + pw), xb = clamp(X(b), x0, x0 + pw);
    if (xb > xa) { g.fillStyle = 'rgba(255,70,100,0.13)'; g.fillRect(xa, 0, xb - xa, ph);
      g.fillStyle = '#ff7a92'; g.font = `600 ${10.5 * d}px system-ui`; if (a > start) g.fillText('seizure onset (annotation)', xa + 5 * d, 12 * d); }
  }
  // time grid
  g.font = `${10 * d}px ui-monospace, monospace`; g.textAlign = 'center';
  for (let t = Math.ceil(start); t <= end; t++) {
    const x = X(t);
    g.strokeStyle = t % 5 === 0 ? '#1f2a44' : '#141c30'; g.lineWidth = d;
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x, ph); g.stroke();
    if (S.seg && t % 2 === 0) { g.fillStyle = '#56627f'; g.fillText(fmtMS(t - S.seg.watch_from_s), x, ph + 14 * d); }
  }
  g.textAlign = 'left';
  // last classified window bracket
  if (S.last) {
    const xa = X(S.last.t_end - 2), xb = X(S.last.t_end);
    const col = S.last.alarm ? '#ff3049' : S.last.dec ? '#ffb21f' : '#4fd8ff';
    g.strokeStyle = col; g.lineWidth = 1.5 * d; g.globalAlpha = 0.85;
    g.beginPath(); g.moveTo(xa, ph - 2 * d); g.lineTo(xa, ph - 7 * d); g.lineTo(xb, ph - 7 * d); g.lineTo(xb, ph - 2 * d); g.stroke();
    g.fillStyle = col; g.font = `${10 * d}px system-ui`; g.fillText('→ FPGA', xb + 4 * d, ph - 4 * d); g.globalAlpha = 1;
  }
  for (let i = 0; i < n; i++) {
    const st = STRIPS[i], y = i * sh, mid = y + sh / 2;
    const color = S.colors[st.color] || (S.colors[st.color] = css(st.color));
    if (i) { g.strokeStyle = '#18213a'; g.lineWidth = d; g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke(); }
    g.fillStyle = color; g.font = `650 ${12.5 * d}px system-ui`; g.fillText(st.name, 10 * d, y + 18 * d);
    g.fillStyle = '#8d9aba'; g.font = `${10.5 * d}px system-ui`; g.fillText(st.sub, 10 * d, y + 32 * d);
    const present = S.seg && sens.has(st.need);
    if (!present) {
      g.fillStyle = '#56627f'; g.font = `italic ${11.5 * d}px system-ui`;
      g.fillText('not recorded for this patient (handled by the missing-sensor rule)', x0 + 12 * d, mid + 4 * d);
      continue;
    }
    if (st.beats) {
      const bpm = heartRate(); g.fillStyle = color; g.font = `600 ${16 * d}px ui-monospace, monospace`;
      g.fillText(bpm ? `${bpm}` : '--', 10 * d, y + 54 * d);
      g.fillStyle = '#8d9aba'; g.font = `${10 * d}px system-ui`; g.fillText('beats/min', 10 * d + g.measureText('000 ').width * 1.6, y + 54 * d);
    }
    g.save(); g.beginPath(); g.rect(x0, y + 2 * d, pw, sh - 4 * d); g.clip();
    const amp = (sh * 0.42);
    if (st.raw) drawTrace(g, st.raw, st.fs, start, end, X, st.motion ? y + sh - 4 * d : mid, amp * 0.9, '#5d6a8a', 1 * d, true, st.motion);
    drawTrace(g, st.filt, st.fs, start, end, X, st.motion ? y + sh - 4 * d : mid, amp, color, 1.4 * d, false, st.motion);
    if (st.alt && S.chunks[st.alt]) drawTrace(g, st.alt, st.fs, start, end, X, y + sh - 4 * d, amp, '#7d5aa8', 1 * d, false, true);
    if (st.beats) {
      g.fillStyle = '#fff';
      for (const bt of S.beats) if (bt > start && bt < end) { g.beginPath(); g.arc(X(bt), y + 10 * d, 2.6 * d, 0, 7); g.fill(); }
    }
    g.restore();
  }
  // "now" sweep
  const xn = X(end);
  const grd = g.createLinearGradient(xn - 40 * d, 0, xn, 0);
  grd.addColorStop(0, 'rgba(79,216,255,0)'); grd.addColorStop(1, 'rgba(79,216,255,0.18)');
  g.fillStyle = grd; g.fillRect(xn - 40 * d, 0, 40 * d, ph);
}
function drawTrace(g, key, fs, start, end, X, base, amp, color, lw, center, motion) {
  const ch = S.chunks[key]; if (!ch) return;
  const sc = stripScale(key);
  g.strokeStyle = color; g.lineWidth = lw; g.lineJoin = 'round'; g.beginPath();
  let first = true;
  for (let b = Math.floor(start); b < end; b++) {
    const arr = ch.get(b); if (!arr) { first = true; continue; }
    let m = 0; if (center) { for (const v of arr) m += v; m /= arr.length; }
    const n = arr.length, stp = n > 64 ? 1 : 1;
    for (let i = 0; i < n; i += stp) {
      const t = b + i / fs; if (t < start - 0.05 || t > end) continue;
      const v = motion ? -(arr[i] / sc) * amp * 1.6 : -((arr[i] - m) / sc) * amp;
      const x = X(t), yy = base + clamp(v, -amp * 2.2, amp * 2.2);
      if (first) { g.moveTo(x, yy); first = false; } else g.lineTo(x, yy);
    }
  }
  g.stroke();
}
function heartRate() {
  const t1 = S.dispEnd, bs = S.beats.filter((b) => b > t1 - 10 && b <= t1);
  if (bs.length < 3) return null;
  const rr = []; for (let i = 1; i < bs.length; i++) rr.push(bs[i] - bs[i - 1]);
  rr.sort((a, b) => a - b);
  const r = rr[Math.floor(rr.length / 2)];
  return r > 0.25 && r < 2.5 ? Math.round(60 / r) : null;
}

// ------------------------------------------------------------------ timeline (canvas)
function drawTimeline() {
  const c = $('tl'), { w, h, d } = sizeCanvas(c), g = c.getContext('2d');
  g.clearRect(0, 0, w, h);
  if (!S.seg) return;
  const t0 = S.seg.watch_from_s, t1 = S.seg.seconds;
  const lx = 38 * d, rx = w - 10 * d, top = 14 * d, bot = h - 18 * d;
  const X = (t) => lx + (t - t0) / (t1 - t0) * (rx - lx);
  const Y = (s) => top + (1 - (s + 25) / 50) * (bot - top);
  for (const [a, b] of S.seg.seizures_s) {
    g.fillStyle = 'rgba(255,70,100,0.15)'; g.fillRect(X(a), top, X(b) - X(a), bot - top);
    g.fillStyle = '#ff7a92'; g.font = `600 ${10 * d}px system-ui`; g.fillText('seizure', X(a) + 4 * d, top + 11 * d);
  }
  g.strokeStyle = '#1f2a44'; g.lineWidth = d;
  for (const s of [-20, -10, 0, 10, 20]) { g.beginPath(); g.moveTo(lx, Y(s)); g.lineTo(rx, Y(s)); g.stroke(); }
  g.fillStyle = '#56627f'; g.font = `${9.5 * d}px ui-monospace, monospace`; g.textAlign = 'right';
  for (const s of [-20, 0, 20]) g.fillText((s > 0 ? '+' : '') + s, lx - 5 * d, Y(s) + 3 * d);
  g.textAlign = 'center';
  const span = t1 - t0, step = span > 600 ? 120 : 60;
  for (let t = 0; t <= span; t += step) g.fillText(fmtMS(t), X(t0 + t), h - 5 * d);
  g.textAlign = 'left';
  const bw = Math.max(1, (rx - lx) / span);
  let prevThr = null;
  for (const e of S.timeline) {
    const [t, s, dec, al, art, tr, thr] = e;
    if (t <= t0) continue;
    const x = X(t);
    g.fillStyle = al ? '#ff3049' : s >= thr ? '#ffb21f' : '#3f8cff';
    const ya = Y(Math.max(s, 0)), yb = Y(Math.min(s, 0));
    g.fillRect(x - bw, ya, bw, Math.max(1, yb - ya));
    if (al) { g.fillStyle = '#ff3049'; g.fillRect(x - bw, top - 9 * d, bw, 5 * d); }
    if (thr !== prevThr && thr !== undefined) {
      if (prevThr !== null) { g.strokeStyle = '#8d9aba'; g.setLineDash([2 * d, 3 * d]); g.beginPath(); g.moveTo(x, top); g.lineTo(x, bot); g.stroke(); g.setLineDash([]); }
      prevThr = thr;
    }
    g.fillStyle = '#ffb21f'; g.fillRect(x - bw, Y(thr) - d * 0.75, bw, 1.5 * d);
  }
  for (const ev of S.events) if (ev.kind === 'button' && ev.t > t0) {
    const x = X(ev.t); g.fillStyle = '#fff'; g.beginPath(); g.moveTo(x, bot); g.lineTo(x - 5 * d, bot + 8 * d); g.lineTo(x + 5 * d, bot + 8 * d); g.fill();
  }
  const xp = X(clamp(S.dispEnd, t0, t1));
  g.strokeStyle = '#e8eeff'; g.lineWidth = 1.5 * d; g.beginPath(); g.moveTo(xp, top - 10 * d); g.lineTo(xp, bot); g.stroke();
  $('tlSub').textContent = `every bar is one 2-second window · ${fmtMS(S.dispEnd - t0)} of ${fmtMS(span)}`;
}

// ------------------------------------------------------------------ FPGA panel
function renderWindow(win) {
  S.last = win;
  const F = S.info.features;
  let ones = 0;
  for (let i = 0; i < F.length; i++) {
    const f = F[i], el = S.featEls[i]; if (!el) continue;
    el.fill.style.width = (100 * clamp((win.f[i] - f.lo) / (f.hi - f.lo), 0, 1)) + '%';
    f.bits.forEach((bj, k) => { const on = win.bits[bj] === '1'; el.ticks[k].classList.toggle('on', on); ones += on; });
  }
  $('bitCount').textContent = ones;
  const bg = S.info.groups.background, sz = S.info.groups.seizure;
  const szEls = $('lutSz').children, bgEls = $('lutBg').children;
  let nsz = 0, nbg = 0;
  for (let i = 0; i < 25; i++) {
    const a = win.luts[sz[0] + i] === '1', b = win.luts[bg[0] + i] === '1';
    szEls[i].classList.toggle('on', a); bgEls[i].classList.toggle('on', b); nsz += a; nbg += b;
  }
  $('nSz').textContent = nsz; $('nBg').textContent = nbg;
  const sn = $('scoreNum'); sn.textContent = (win.score > 0 ? '+' : '') + win.score;
  sn.className = win.alarm ? 'al' : win.score >= win.thr ? 'hi' : '';
  const f = $('gFill'), v = clamp(win.score, -25, 25);
  f.style.left = (v >= 0 ? 50 : 50 + v / 25 * 50) + '%'; f.style.width = Math.abs(v) / 25 * 50 + '%';
  f.style.background = win.alarm ? '#ff3049' : win.score >= win.thr ? '#ffb21f' : '#3f8cff';
  $('gThr').style.left = (50 + clamp(win.thr, -25, 25) / 25 * 50) + '%';
  $('gThrLab').textContent = `threshold ${win.thr}`;
  const hist = win.hist || [], cells = $('hist').querySelectorAll('.hcell');
  const pad = 10 - hist.length;
  cells.forEach((c, i) => c.classList.toggle('on', i >= pad && hist[i - pad] === 1));
  $('hist').classList.toggle('alarm', !!win.alarm);
  $('hres').textContent = win.alarm ? 'ALARM' : 'no alarm';
  $('kHint').textContent = `alarm when ${win.k} of the last 10 windows say seizure`;
  $('winLabel').textContent = `window ${win.w + 1 - S.seg.watch_from_s > 0 ? '#' + (win.w + 1 - S.seg.watch_from_s) : ''} · seconds ${fmtMS(win.t_end - 2 - S.seg.watch_from_s)} to ${fmtMS(win.t_end - S.seg.watch_from_s)}`;
  setChip('chipCheck', win.ok && win.n_match === win.n_win ? 'good' : 'bad', `${win.n_match} / ${win.n_win} windows identical`);
  $('stWin').textContent = (S.nwinHw || win.n_win).toLocaleString();
  setAlarm(win.alarm);
  S.virt.flash = performance.now() + 90;
}
function setChip(id, cls, text) { const c = $(id); c.className = 'chip ' + cls; c.querySelector('span').textContent = text; }

// ------------------------------------------------------------------ alarm + sound
function setAlarm(on) {
  if (on === S.alarm) return;
  S.alarm = on;
  document.body.classList.toggle('alarm', !!on);
  if (on) beepLoop();
}
function unlockAudio() {
  if (!S.audio) { try { S.audio = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { S.audio = null; } }
  if (S.audio && S.audio.state === 'suspended') S.audio.resume();
}
function beep(f, t, dur) {
  const a = S.audio, o = a.createOscillator(), gn = a.createGain();
  o.type = 'square'; o.frequency.value = f; gn.gain.value = 0.0001;
  o.connect(gn); gn.connect(a.destination);
  gn.gain.setValueAtTime(0.0001, t); gn.gain.exponentialRampToValueAtTime(0.12, t + 0.01);
  gn.gain.exponentialRampToValueAtTime(0.0001, t + dur); o.start(t); o.stop(t + dur + 0.02);
}
function beepLoop() {
  if (!S.alarm) return;
  if (S.sound && S.audio && S.audio.state === 'running') {
    const t = S.audio.currentTime; beep(1046, t, 0.12); beep(1046, t + 0.2, 0.12);
  }
  setTimeout(beepLoop, 800);
}

// ------------------------------------------------------------------ messages
function resetView() {
  S.chunks = {}; S.scales = {}; S.beats = []; S.last = null; S.timeline = []; S.events = []; S.nAlarm = 0;
  S.onsetToasted = {}; setAlarm(0);
  $('stAlarm').textContent = '0';
  if (S.featEls) for (const e of S.featEls) { e.fill.style.width = '0'; e.ticks.forEach((t) => t.classList.remove('on')); }
  for (const id of ['lutSz', 'lutBg']) for (const c of $(id).children) c.classList.remove('on');
  $('hist').querySelectorAll('.hcell').forEach((c) => c.classList.remove('on'));
  $('scoreNum').textContent = '–';
}
function setSegment(seg) {
  S.seg = seg;
  $('segTitle').textContent = seg.title;
  $('segSub').textContent = `${seg.recording.replace('_', ' · ')} · ${seg.story}`;
}
function onMsg(m) {
  switch (m.type) {
    case 'state':
      S.phase = m.phase; S.playing = m.playing; S.speed = m.speed; S.op = m.op;
      if (m.segment) {
        resetView(); setSegment(m.segment); S.timeline = m.timeline || []; S.events = m.events || [];
        S.pos = m.pos; S.recvEnd = m.pos; S.dispEnd = m.pos;
        S.nAlarm = S.events.filter((e) => e.kind === 'alarm' && e.watched).length; $('stAlarm').textContent = S.nAlarm;
      }
      break;
    case 'load':
      resetView(); setSegment(m.segment); S.phase = 'warmup'; S.op = m.op;
      S.recvEnd = S.dispEnd = 0; $('endBox').classList.remove('show');
      $('warmWho').textContent = m.segment.title.split(':')[0];
      break;
    case 'live':
      S.phase = 'live'; S.timeline = m.timeline || []; S.pos = m.pos; S.recvEnd = m.pos; S.dispEnd = m.pos - 0.001;
      break;
    case 'frame': {
      const b = m.b;
      for (const [k, v] of Object.entries(m.sig)) if (k !== 'beats') pushChunk(k, b, v);
      for (const off of (m.sig.beats || [])) S.beats.push(b + off / 256);
      S.beats = S.beats.filter((t) => t > b - VIEW_S - 3);
      S.recvEnd = b + 1; S.pos = b + 1; S.speed = m.speed;
      if (S.recvEnd - S.dispEnd > 2.5 || S.dispEnd > S.recvEnd) S.dispEnd = S.recvEnd - 1;
      for (const e of (m.prev || [])) S.timeline.push(e);
      if (m.win) {
        const w = m.win; S.timeline.push([w.t_end, w.score, w.dec, w.alarm, w.art[0] + w.art[1], w.truth, w.thr]);
        renderWindow(w);
      }
      spawnPackets(m.win);
      for (const [a] of S.seg.seizures_s) if (b + 1 >= a && b < a + 1.5 && !S.onsetToasted[a]) {
        S.onsetToasted[a] = 1; toast('<b>Seizure begins</b> here according to the neurologist\'s annotation. The detector never sees this label.', 'warn');
      }
      break;
    }
    case 'ff':
      for (const e of m.wins) S.timeline.push(e);
      S.chunks = {}; S.beats = []; S.recvEnd = m.pos; S.dispEnd = m.pos - 0.001; S.pos = m.pos;
      if (m.last) renderWindow(m.last);
      break;
    case 'tick':
      S.phase = m.phase; S.playing = m.playing; S.speed = m.speed; S.op = m.op;
      if (m.io !== undefined) S.io = m.io;
      if (m.board_leds) S.boardLeds = m.board_leds;
      if (m.rtt_us) S.rtt = m.rtt_us;
      if (m.lat) S.lat = m.lat;
      if (m.nwin_hw !== undefined) S.nwinHw = m.nwin_hw;
      if (m.warm) { $('warmBar').style.width = (100 * m.warm[0] / m.warm[1]) + '%'; $('warmN').textContent = `${m.warm[0]} / ${m.warm[1]} seconds processed`; }
      if (m.btn) $('bButton').classList.add('press'); else $('bButton').classList.remove('press');
      break;
    case 'event':
      if (m.kind === 'button') {
        S.events.push(m); toast(`<b>Patient button pressed</b> (${m.source}) at ${fmtMS(m.t - S.seg.watch_from_s)}`);
      } else if (m.kind === 'alarm_end') {
        // the banner follows the window results
      } else if (m.kind === 'alarm') {
        S.events.push(m);
        if (m.watched) { S.nAlarm++; $('stAlarm').textContent = S.nAlarm; }
        if (m.true) {
          const a = m.after_onset;
          $('alarmSub').textContent = a >= 0 ? `${Math.round(a)} s after the annotated onset · raised by the FPGA core` : 'raised by the FPGA core';
          if (m.watched) toast(`<b>Seizure detected</b> ${a >= 0 ? Math.round(a) + ' s after the annotated onset' : 'before the annotated onset'}.`, 'good');
        } else {
          $('alarmSub').textContent = 'outside the annotated seizure (false alarm)';
          if (m.watched) toast('<b>Alarm outside the annotated seizure</b> (a false alarm).', 'bad');
        }
      }
      break;
    case 'op':
      S.op = m.op; toast(`Operating point: <b>${OP_LABEL[m.op]}</b>. ${OP_TIP[m.op]}.`);
      break;
    case 'ended': showSummary(m.summary); break;
    case 'error': toast('⚠ ' + m.msg, 'bad'); break;
  }
}
function showSummary(s) {
  const seg = S.seg; if (!seg) return;
  let head, cls;
  const alarms = s.alarms || [];
  const tp = alarms.find((a) => a.true);
  if (seg.seizures_s.length) {
    if (tp) { head = `Seizure detected ${Math.round(tp.after_onset)} s after the annotated onset`; cls = 'good'; }
    else { head = `Seizure missed at the ${OP_LABEL[s.op]} setting`; cls = 'bad'; }
  } else { head = s.false_alarms ? `${s.false_alarms} false alarm(s)` : 'No alarm during normal activity'; cls = s.false_alarms ? 'bad' : 'good'; }
  $('endTitle').textContent = seg.title;
  const rows = [
    ['operating point', OP_LABEL[s.op]], ['false alarms', s.false_alarms],
    ['windows classified (incl. calibration)', s.windows.toLocaleString()],
    ['FPGA result = software model', `${s.match.toLocaleString()} / ${s.windows.toLocaleString()}`],
  ];
  $('endBody').innerHTML = `<div class="big-result ${cls}">${head}</div>` + rows.map(([a, b]) => `<div class="endrow"><span>${a}</span><b>${b}</b></div>`).join('') +
    (cls === 'bad' && seg.seizures_s.length ? '<p style="margin-top:12px;color:var(--muted)">Try the Sensitive operating point and play it again.</p>' : '');
  setTimeout(() => $('endBox').classList.add('show'), 1200);
}

// ------------------------------------------------------------------ frame loop
let lastT = performance.now();
function loop(now) {
  const dt = Math.min(0.1, (now - lastT) / 1000); lastT = now;
  if (S.playing && S.phase === 'live') S.dispEnd = Math.min(S.recvEnd, S.dispEnd + dt * S.speed);
  document.body.classList.toggle('playing', S.playing);
  $('bPlay').textContent = S.playing ? '❚❚ Pause' : (S.phase === 'ended' ? '↺ Replay' : '▶ Play');
  for (const b of $('speeds').children) b.classList.toggle('on', +b.dataset.v === S.speed);
  for (const b of $('ops').children) b.classList.toggle('on', b.dataset.v === S.op);
  $('warm').classList.toggle('show', S.phase === 'warmup' && !$('chooser').classList.contains('show'));
  if (S.seg) {
    $('recClock').textContent = fmtHMS(S.seg.record_start_s + S.dispEnd);
    $('recClockSub').textContent = `into recording ${S.seg.recording}`;
  }
  if (S.rtt) $('stRtt').textContent = `${S.rtt.toFixed(0)} µs`;
  $('stLat').textContent = `${S.lat} cycles · ${S.lat * 10} ns`;
  drawSignals(); drawTimeline(); drawPipe(now); renderLeds(now);
  requestAnimationFrame(loop);
}

// ------------------------------------------------------------------ start
async function start() {
  S.info = await (await fetch('/api/info')).json();
  buildFeatures(); buildLuts(); buildControls(); buildChooser(); buildBoard();
  const onBoard = !S.info.platform.includes('no board');
  setChip('chipBoard', onBoard ? 'good' : 'warn', onBoard ? S.info.platform.replace('Xilinx ', '') : 'laptop rehearsal (no board)');
  setChip('chipCore', S.info.backend === 'fpga' ? 'good' : 'warn',
    S.info.backend === 'fpga' ? 'FPGA core · 100 MHz' : 'software model (no FPGA)');
  $('chipCore').title = S.info.backend_label;
  const es = new EventSource('/api/stream');
  let lostTimer = null;
  es.onopen = () => { S.connected = true; clearTimeout(lostTimer); $('lost').classList.remove('show'); };
  es.onerror = () => { S.connected = false; clearTimeout(lostTimer); lostTimer = setTimeout(() => { if (!S.connected) $('lost').classList.add('show'); }, 2500); };
  es.onmessage = (e) => { try { onMsg(JSON.parse(e.data)); } catch (err) { console.error(err); } };
  window.addEventListener('resize', () => { S.colors = {}; layoutFeatures(); });
  if (new URLSearchParams(location.search).has('choose')) showChooser(true);
  requestAnimationFrame(loop);
}
start();
