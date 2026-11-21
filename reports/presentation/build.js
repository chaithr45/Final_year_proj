const pptxgen = require("pptxgenjs");
const path = require("path");
const { applyTheme } = require(process.env.APPLY_THEME || "./apply_theme.js");

const FIG = "/home/user/Final_year_proj/reports/bisp/figures/";
const OUT = path.join(__dirname, "SeizeLUT_Project_Presentation.pptx");

const THEME = {
  name: "SeizeLUT",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1B2430", lt1: "FFFFFF", dk2: "13202E", lt2: "EEF2F6",
    accent1: "E8703A", accent2: "2F6690", accent3: "8A96A6", accent4: "A8461A",
    accent5: "5B7A99", accent6: "BFCBD8", hlink: "2F6690", folHlink: "5B7A99",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.author = "Akshara Bonam, Sowjanya, Sai Chaithr";
pres.title = "SeizeLUT: Project Presentation";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

const FOOT = "SeizeLUT · BISP Project · ECE, NIT Warangal";

pres.defineSlideMaster({
  title: "TITLE_DARK",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.7, y: 2.0, w: 9.2, h: 1.6, fontSize: 44, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.7, y: 3.75, w: 9.2, h: 1.2, fontSize: 20, color: C.accent6, valign: "top", margin: 0 }, text: "" } },
  ],
});

pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.background1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.8, fontSize: 32, bold: true, color: C.text2, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: { text: FOOT, options: { x: 0.6, y: 7.0, w: 8, h: 0.3, fontSize: 10, color: C.accent3, margin: 0 } } },
  ],
  slideNumber: { x: 12.2, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: C.accent3, align: "right" },
});

pres.defineSlideMaster({
  title: "SECTION_DARK",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.8, fontSize: 32, bold: true, color: C.background1, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: { text: FOOT, options: { x: 0.6, y: 7.0, w: 8, h: 0.3, fontSize: 10, color: C.accent6, margin: 0 } } },
  ],
  slideNumber: { x: 12.2, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: C.accent6, align: "right" },
});

// helpers
function card(slide, x, y, w, h, name, dark) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.12, objectName: name,
    fill: { color: dark ? C.accent2 : C.background2 }, line: { color: dark ? C.accent2 : C.background2 },
  });
}
function stat(slide, x, y, w, num, label, name, onDark) {
  slide.addText(num, { x, y, w, h: 0.8, fontSize: 40, bold: true, fontFace: THEME.headFontFace, color: onDark ? C.accent1 : C.accent4, margin: 0, isTextBox: true, objectName: name + " number" });
  slide.addText(label, { x, y: y + 0.82, w, h: 0.75, fontSize: 14, color: onDark ? C.accent6 : C.text1, margin: 0, valign: "top", isTextBox: true, objectName: name + " label" });
}
function numCircle(slide, x, y, n, name) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: 0.5, h: 0.5, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: name });
  slide.addText(String(n), { x, y, w: 0.5, h: 0.5, fontSize: 16, bold: true, color: C.text2, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: name + " text" });
}
function img(slide, file, x, y, w, h, alt, name) {
  slide.addImage({ path: FIG + file, x, y, w, h, altText: alt, objectName: name });
}
function fitImg(slide, file, pw, ph, bx, by, bw, bh, alt, name) {
  const r = Math.min(bw / pw, bh / ph);
  const w = pw * r, h = ph * r;
  img(slide, file, bx + (bw - w) / 2, by + (bh - h) / 2, w, h, alt, name);
}

// ---------------------------------------------------------------- 1 Title
pres.addSection({ title: "Introduction" });
let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Introduction" });
s.addText("SeizeLUT", { x: 0.7, y: 0.7, w: 6, h: 0.5, fontSize: 18, bold: true, color: C.accent1, margin: 0, isTextBox: true, charSpacing: 4, objectName: "Eyebrow" });
s.addText("A Self-Testing, Multiplier-Free Seizure Detector on an FPGA with Doctor Alerts", { placeholder: "title" });
s.addText("BISP Project · B.Tech, Electronics and Communication Engineering · NIT Warangal", { placeholder: "body" });
s.addText([
  { text: "Akshara Bonam (23ECB0A11)", options: { breakLine: true } },
  { text: "Sowjanya (23ECB0A22)", options: { breakLine: true } },
  { text: "Sai Chaithr (23ECB0A20)", options: { breakLine: true } },
  { text: "Guide: [Name], Department of ECE" },
], { x: 0.7, y: 5.1, w: 7, h: 1.6, fontSize: 16, color: C.background1, margin: 0, valign: "top", isTextBox: true, objectName: "Team" });
s.addShape(pres.shapes.OVAL, { x: 10.3, y: 2.2, w: 2.4, h: 2.4, fill: { color: C.background1 }, line: { color: C.background1 }, objectName: "Logo backdrop" });
img(s, "nitw_logo.png", 10.85, 2.55, 1.3, 1.3 * 972 / 828, "NIT Warangal logo", "NITW logo");
s.addNotes("Introduce the team and the project: a seizure detector that runs inside an FPGA's lookup tables, tests itself, and alerts a doctor.");

// ---------------------------------------------------------------- 2 Problem
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Introduction" });
s.addText("Problem and motivation", { placeholder: "title" });
const probs = [
  ["Seizures go unnoticed", "Many seizures happen at night or alone; patients and diaries miss them. A wearable detector can raise help."],
  ["Wearables need tiny, low-power hardware", "Deep networks need multipliers and memory; a body-worn device has little of either."],
  ["False alarms make devices useless", "An alarm that rings many times a day is switched off, so false alarms per day matter as much as sensitivity."],
  ["A silent failure looks like a quiet night", "If the detector hardware breaks, it simply stays quiet. The device must be able to test itself."],
];
probs.forEach((p, i) => {
  const x = 0.6 + (i % 2) * 6.15, y = 1.45 + Math.floor(i / 2) * 2.7;
  card(s, x, y, 5.95, 2.45, "Problem card " + (i + 1));
  numCircle(s, x + 0.3, y + 0.3, i + 1, "Problem number " + (i + 1));
  s.addText(p[0], { x: x + 1.0, y: y + 0.28, w: 4.7, h: 0.6, fontSize: 20, bold: true, color: C.text2, margin: 0, valign: "middle", isTextBox: true, objectName: "Problem title " + (i + 1) });
  s.addText(p[1], { x: x + 1.0, y: y + 0.95, w: 4.7, h: 1.3, fontSize: 15, color: C.text1, margin: 0, valign: "top", isTextBox: true, objectName: "Problem text " + (i + 1) });
});
s.addNotes("Four problems drive the design: unnoticed seizures, hardware limits of wearables, false alarms, and silent hardware failure.");

// ---------------------------------------------------------------- 3 Objectives
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Introduction" });
s.addText("Objectives", { placeholder: "title" });
const objs = [
  "Detect seizures from wearable signals (behind-the-ear EEG, ECG, EMG, motion) on the public SeizeIT2 dataset, with the official train/test split",
  "Build the classifier natively from FPGA lookup tables (LUT6), with no multipliers, and compare it with published methods",
  "Put the whole detector, front end and classifier, in the fabric of an AMD Kria KV260 and verify it bit-exactly on the board",
  "Add a built-in self-test that detects every hardware fault that can change a decision",
  "Raise a local alarm (LED, buzzer) and a doctor alert on a phone through an ESP32",
];
objs.forEach((o, i) => {
  const y = 1.45 + i * 1.08;
  numCircle(s, 0.7, y + 0.12, i + 1, "Objective number " + (i + 1));
  s.addText(o, { x: 1.45, y, w: 11.2, h: 0.75, fontSize: 18, color: C.text1, margin: 0, valign: "middle", isTextBox: true, objectName: "Objective " + (i + 1) });
});
s.addNotes("Five objectives: detection on SeizeIT2, LUT-native classifier, whole detector in the FPGA, self-test, and alerts.");

// ---------------------------------------------------------------- 4 Dataset
pres.addSection({ title: "Method" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Method" });
s.addText("Dataset: SeizeIT2 (OpenNeuro ds005873)", { placeholder: "title" });
const ds = [["125", "patients, wearable recordings"], ["11,626 h", "of EEG (median 95 h per patient)"], ["883", "seizures: 702 training, 181 test"], ["96 / 29", "training / test patients (official split; test sub-097 to sub-125)"]];
ds.forEach((d, i) => {
  const y = 1.45 + i * 1.3;
  stat(s, 0.7, y, 3.6, d[0], d[1], "Dataset stat " + (i + 1));
});
fitImg(s, "hours_and_seizures_per_patient.png", 1200, 480, 4.6, 1.5, 8.1, 3.6, "Hours recorded per patient (bars; blue training, orange test) and seizures per patient (dots)", "Hours per patient chart");
s.addText("Hours recorded per patient (bars: blue training, orange test) and seizures per patient (dots). Every design choice was made on the 96 training patients; the 29 test patients were scored once at the end.", { x: 4.6, y: 5.3, w: 8.1, h: 1.0, fontSize: 13, color: C.accent3, margin: 0, valign: "top", isTextBox: true, objectName: "Dataset caption" });
s.addNotes("SeizeIT2 is the largest public wearable seizure dataset. We kept the official split: the test patients were used only once, for the final evaluation.");

// ---------------------------------------------------------------- 5 System overview
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Method" });
s.addText("System overview", { placeholder: "title" });
const flow = [["Sense", "Behind-the-ear EEG (2 channels), ECG, EMG, accelerometer and gyroscope"], ["Features", "38 integer features per 1-s window: shift-add filters, no multipliers"], ["Compare", "146 learned thresholds turn features into bits"], ["Decide", "50 LUT6 vote; popcount gives the score"], ["Alarm", "10 of 10 high windows: LED, buzzer, ESP32 doctor alert"]];
flow.forEach((f, i) => {
  const x = 0.6 + i * 2.5;
  card(s, x, 1.5, 2.1, 3.0, "Flow card " + (i + 1), i === 4);
  numCircle(s, x + 0.2, 1.7, i + 1, "Flow number " + (i + 1));
  s.addText(f[0], { x: x + 0.2, y: 2.35, w: 1.75, h: 0.5, fontSize: 20, bold: true, color: i === 4 ? C.background1 : C.text2, margin: 0, isTextBox: true, objectName: "Flow title " + (i + 1) });
  s.addText(f[1], { x: x + 0.2, y: 2.9, w: 1.75, h: 1.5, fontSize: 14, color: i === 4 ? C.background1 : C.text1, margin: 0, valign: "top", isTextBox: true, objectName: "Flow text " + (i + 1) });
  if (i < 4) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 2.15, y: 2.8, w: 0.3, h: 0.4, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: "Flow arrow " + (i + 1) });
});
const facts = [["Bit-exact everywhere", "Python, C, Verilog and the board give the same integers for every window"], ["All in the fabric", "Front end and classifier run in the FPGA; the Arm cores only move raw samples"], ["Verified on hardware", "Every stage is checked against the software model on the KV260"]];
facts.forEach((f, i) => {
  const x = 0.6 + i * 4.1;
  s.addText(f[0], { x, y: 4.95, w: 3.8, h: 0.45, fontSize: 18, bold: true, color: C.accent4, margin: 0, isTextBox: true, objectName: "Fact title " + (i + 1) });
  s.addText(f[1], { x, y: 5.45, w: 3.8, h: 1.0, fontSize: 14, color: C.text1, margin: 0, valign: "top", isTextBox: true, objectName: "Fact text " + (i + 1) });
});
s.addNotes("Signals are cut into one-second windows, turned into 38 integer features, compared with learned thresholds, and passed to 50 lookup tables whose votes form a score. Ten high windows in a row raise the alarm.");

// ---------------------------------------------------------------- 6 Method details
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Method" });
s.addText("Method: a LUT-native classifier", { placeholder: "title" });
const meth = [
  ["Integer front end", "38 features (EEG line length and band power, heart rate from ECG, EMG power, movement) computed in fixed point, identical in Python, C and hardware."],
  ["Thermometer encoding", "146 learned thresholds turn the features into bits; each comparator is one small block of logic."],
  ["Differentiable Weightless Network (DWN)", "50 lookup tables of 6 inputs each, trained end to end with distillation from a stronger model; the trained truth tables are loaded straight into FPGA LUT6s."],
  ["Decision and alarm", "Popcount of the 50 outputs gives a score; frozen and programmable operating points; the alarm needs 10 of 10 high windows."],
];
meth.forEach((m, i) => {
  const y = 1.4 + i * 1.35;
  numCircle(s, 0.7, y + 0.1, i + 1, "Method number " + (i + 1));
  s.addText(m[0], { x: 1.45, y, w: 6.2, h: 0.45, fontSize: 19, bold: true, color: C.text2, margin: 0, isTextBox: true, objectName: "Method title " + (i + 1) });
  s.addText(m[1], { x: 1.45, y: y + 0.45, w: 6.2, h: 0.85, fontSize: 14, color: C.text1, margin: 0, valign: "top", isTextBox: true, objectName: "Method text " + (i + 1) });
});
card(s, 8.2, 1.4, 4.5, 5.2, "Method stats card", true);
stat(s, 8.55, 1.7, 3.9, "50 LUT6", "decide seizure or not", "Stat LUTs", true);
stat(s, 8.55, 3.3, 3.9, "3 cycles", "latency of the classifier on the FPGA", "Stat latency", true);
stat(s, 8.55, 4.9, 3.9, "0 DSP", "no multipliers in the whole detector", "Stat DSP", true);
s.addNotes("The key idea: the network is made of the FPGA's own building block, the 6-input lookup table, so the trained model maps one to one onto hardware.");

// ---------------------------------------------------------------- 7 Results F1
pres.addSection({ title: "Results" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
s.addText("Results on the 29 test patients", { placeholder: "title" });
fitImg(s, "test_f1.png", 1740, 1080, 0.6, 1.35, 7.4, 5.4, "Event-F1 on the test patients for all models", "Test F1 chart");
card(s, 8.4, 1.4, 4.3, 5.25, "Results card");
stat(s, 8.75, 1.65, 3.7, "0.248", "event-F1 of the final DWN (± 0.016 over 5 seeds)", "Stat F1");
stat(s, 8.75, 3.25, 3.7, "0.8 / day", "false alarms at the default operating point", "Stat FA");
s.addText("Larger software models score higher (LightGBM 0.308), but need far more hardware. The DWN is the best model per lookup table.", { x: 8.75, y: 4.9, w: 3.7, h: 1.6, fontSize: 14, color: C.text1, margin: 0, valign: "top", isTextBox: true, objectName: "Results note" });
s.addNotes("Final test, scored once with 5 seeds. The DWN gives event-F1 0.248 with 0.8 false alarms per day. We report honestly that LightGBM scores 0.308, but it is not LUT-native.");

// ---------------------------------------------------------------- 8 Sensitivity / FA
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
s.addText("Sensitivity against false alarms", { placeholder: "title" });
fitImg(s, "sens_fa_test.png", 1620, 1320, 0.6, 1.35, 6.4, 5.45, "Sensitivity against false alarms per hour on the test patients", "Sensitivity chart");
s.addTable([
  [{ text: "Operating point", options: { bold: true, color: C.background1, fill: { color: C.text2 } } },
   { text: "Seizures found", options: { bold: true, color: C.background1, fill: { color: C.text2 } } },
   { text: "False alarms", options: { bold: true, color: C.background1, fill: { color: C.text2 } } }],
  ["DWN, default (frozen)", "25.5 %", "0.8 per day"],
  ["DWN at 1.2 FA/h", "43.2 %", "1.2 per hour"],
  ["ChronoNet (clean) at 1.2 FA/h", "34.8 %", "1.2 per hour"],
  ["Two-stage (post-ictal check)", "73.3 % ± 1.4", "10.9 per hour"],
  ["SeizeIT2 paper's SVM", "71.1 %", "11.0 per hour"],
], { x: 7.3, y: 1.45, w: 5.4, colW: [2.5, 1.45, 1.45], fontSize: 14, color: C.text1, border: { type: "solid", pt: 0.5, color: "BFCBD8" }, fill: { color: C.background1 }, rowH: 0.5, objectName: "Operating points table" });
s.addText("Any-overlap sensitivity on the test patients. At the same false-alarm rate the DWN finds more seizures than ChronoNet, and the two-stage detector beats the dataset paper's SVM.", { x: 7.3, y: 4.85, w: 5.4, h: 1.5, fontSize: 14, color: C.text1, margin: 0, valign: "top", isTextBox: true, objectName: "Sensitivity note" });
s.addNotes("One detector, several operating points. Home use wants few false alarms; hospital monitoring can accept more to catch more seizures.");

// ---------------------------------------------------------------- 9 Hardware cost
pres.addSection({ title: "Hardware" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Hardware" });
s.addText("Hardware cost of LUT-native classifiers", { placeholder: "title" });
s.addChart(pres.charts.BAR, [{ name: "LUTs", labels: ["DWN (ours)", "TreeLUT", "Logic-gate network"], values: [398, 2677, 5249] }], {
  x: 0.6, y: 1.35, w: 7.0, h: 5.3, barDir: "bar", objectName: "LUT cost chart",
  showTitle: true, title: "LUTs on the XCK26 (Vivado, out of context)", titleFontSize: 14, titleColor: "1B2430", titleFontFace: "+mn-lt",
  showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 13, dataLabelColor: "1B2430", dataLabelFontFace: "+mn-lt",
  chartColors: ["E8703A", "8A96A6", "8A96A6"], invertedColors: ["E8703A"],
  catAxisLabelColor: "4A5566", valAxisLabelColor: "4A5566", catAxisLabelFontSize: 13, valAxisLabelFontSize: 11,
  catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisOrientation: "maxMin",
  valGridLine: { color: "E1E6EC", size: 0.5 }, catGridLine: { style: "none" }, showLegend: false, varyColors: true,
});
s.addTable([
  [{ text: "Part", options: { bold: true, color: C.background1, fill: { color: C.text2 } } },
   { text: "Cost", options: { bold: true, color: C.background1, fill: { color: C.text2 } } }],
  ["DWN classifier", "398 LUTs, 468 MHz, 17 mW"],
  ["Feature engine", "804 LUTs, 4.5 BRAM, 234 MHz"],
  ["Whole detector", "1,202 LUTs, no multiplier"],
  ["Full KV260 design", "3,796 LUTs (3.2 %), 0 DSP"],
], { x: 8.0, y: 1.45, w: 4.7, colW: [1.9, 2.8], fontSize: 14, color: C.text1, border: { type: "solid", pt: 0.5, color: "BFCBD8" }, fill: { color: C.background1 }, rowH: 0.5, objectName: "Cost table" });
s.addText("The DWN needs 6.7× fewer LUTs than TreeLUT and 13.2× fewer than the logic-gate network, and is also the fastest. Yosys gives the same total (797 + 405 = 1,202).", { x: 8.0, y: 4.3, w: 4.7, h: 1.8, fontSize: 14, color: C.text1, margin: 0, valign: "top", isTextBox: true, objectName: "Cost note" });
s.addNotes("Three LUT-native models synthesised the same way. The DWN is 6.7 times smaller than TreeLUT and 13 times smaller than the logic-gate network. The whole detector is 1,202 LUTs.");

// ---------------------------------------------------------------- 10 FPGA implementation
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Hardware" });
s.addText("Whole detector in the FPGA fabric (AMD Kria KV260)", { placeholder: "title" });
const hw = [
  ["Feature engine", "Microcoded shift-add engine: one 40-bit adder, 2,323 instructions, 930-word register file. Every filter coefficient is a sum of at most five powers of two, so no multipliers."],
  ["Classifier core", "146 comparators, 50 LUT6, popcount score, frozen and programmable operating points; result 3 cycles after the features."],
  ["Test and debug logic", "Built-in self-test with its vector ROM, fault-injection registers, read-back of every comparator bit and LUT output."],
  ["Interface and demo I/O", "AXI4-Lite at 100 MHz (8 KB window); the Arm cores only move raw samples. PMOD pins drive an LED, buzzer and the ESP32 alarm wire."],
];
hw.forEach((h, i) => {
  const x = 0.6 + (i % 2) * 6.15, y = 1.4 + Math.floor(i / 2) * 2.75;
  card(s, x, y, 5.95, 2.5, "Hardware card " + (i + 1), i === 0);
  s.addText(h[0], { x: x + 0.3, y: y + 0.25, w: 5.35, h: 0.5, fontSize: 20, bold: true, color: i === 0 ? C.background1 : C.text2, margin: 0, isTextBox: true, objectName: "Hardware title " + (i + 1) });
  s.addText(h[1], { x: x + 0.3, y: y + 0.85, w: 5.35, h: 1.5, fontSize: 15, color: i === 0 ? C.background1 : C.text1, margin: 0, valign: "top", isTextBox: true, objectName: "Hardware text " + (i + 1) });
});
s.addNotes("In the final design the Arm cores only pass raw samples. The feature engine and the classifier both run in the fabric. The engine needs under one million cycles per second of signal.");

// ---------------------------------------------------------------- 11 Self-test
s = pres.addSlide({ masterName: "SECTION_DARK", sectionTitle: "Hardware" });
s.addText("Built-in self-test: no silent failures", { placeholder: "title" });
s.addChart(pres.charts.BAR, [{ name: "Faults detected (%)", labels: ["1,024 consecutive windows", "Random windows", "255 selected windows (ours)"], values: [50.7, 82.2, 100.0] }], {
  x: 0.6, y: 1.35, w: 7.4, h: 5.3, barDir: "bar", objectName: "Fault coverage chart",
  showTitle: true, title: "Decision-relevant faults detected (%)", titleFontSize: 14, titleColor: "EEF2F6", titleFontFace: "+mn-lt",
  showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 13, dataLabelColor: "EEF2F6", dataLabelFontFace: "+mn-lt", dataLabelFormatCode: "0.0",
  chartColors: ["8A96A6", "8A96A6", "E8703A"], varyColors: true,
  catAxisLabelColor: "BFCBD8", valAxisLabelColor: "BFCBD8", catAxisLabelFontSize: 13, valAxisLabelFontSize: 11,
  catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisOrientation: "maxMin", valAxisMaxVal: 100, valAxisMinVal: 0,
  valGridLine: { color: "2E4459", size: 0.5 }, catGridLine: { style: "none" }, showLegend: false,
});
stat(s, 8.5, 1.5, 4.2, "3,592", "single faults: 3,200 truth-table bit flips + 392 stuck-at outputs; 2,890 change a decision", "Stat faults", true);
stat(s, 8.5, 3.25, 4.2, "10.3 µs", "on-chip self-test: 1,024 vectors in 1,028 cycles, fast enough after every 1-s window", "Stat BIST", true);
stat(s, 8.5, 5.0, 4.2, "88 s", "all 3,592 faults injected on the board: 0 hardware/software mismatches", "Stat board faults", true);
s.addNotes("We simulated every single fault on 31.4 million training windows. The obvious test, replaying consecutive recorded windows, detects only half of the faults that change a decision. Our 255 selected windows detect all of them, and the on-chip self-test takes 10.3 microseconds.");

// ---------------------------------------------------------------- 12 Board results
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Hardware" });
s.addText("Board test campaign: 9 of 9 pass", { placeholder: "title" });
const hdr = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text2 } } });
s.addTable([
  [hdr("Step"), hdr("Measured on the KV260"), hdr("Result")],
  ["1 Identity", "Core version 3, 38 features, 50 LUTs; bitstream loads in 4.4 s", "PASS"],
  ["2 Self-test", "1,024 of 1,024 vectors correct in 1,028 cycles", "PASS"],
  ["3 Latency", "3 clock cycles (30 ns)", "PASS"],
  ["4 Replay", "431,960 windows of 10 recordings: 0 mismatches; 3.2 µs per window", "PASS"],
  ["5 Detection", "Equal to simulation on 10 recordings (frozen: 1 of 19 seizures, 0 false alarms in 120 h)", "Reported"],
  ["6 Power", "3.069 W idle, 3.074 W with the classifier busy", "Reported"],
  ["7 Front end on Arm", "0 feature and 0 output mismatches", "PASS"],
  ["8 Fault injection", "3,592 faults: 0 mismatches; all 2,890 decision-relevant faults detected", "PASS"],
  ["9 Whole detector in fabric", "9,214 windows from raw samples: 0 mismatches; 102–124× real time", "PASS"],
], { x: 0.6, y: 1.35, w: 12.1, colW: [2.6, 8.0, 1.5], fontSize: 13, color: C.text1, border: { type: "solid", pt: 0.5, color: "BFCBD8" }, fill: { color: C.background1 }, rowH: 0.48, objectName: "Board results table" });
s.addNotes("One script runs nine tests on the board. Steps 5 and 6 are measurements, the others are pass or fail. The board reproduces the software exactly.");

// ---------------------------------------------------------------- 13 Demo and alert
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Hardware" });
s.addText("Live demo and doctor alert", { placeholder: "title" });
fitImg(s, "dashboard_rehearsal.png", 1440, 900, 0.6, 1.35, 6.0, 4.1, "Live dashboard showing signals, features, LUT votes and the alarm", "Dashboard screenshot");
fitImg(s, "alert_page.png", 2370, 1992, 6.9, 1.35, 5.8, 4.1, "Doctor alert page on a phone at a new seizure and in an emergency", "Alert page screenshot");
s.addText("Dashboard: recorded test signals stream through the board; every stage is shown and every window is checked against software. On the breadboard the FPGA drives a red LED and a buzzer (BC547).", { x: 0.6, y: 5.6, w: 6.0, h: 1.2, fontSize: 13, color: C.text1, margin: 0, valign: "top", isTextBox: true, objectName: "Dashboard caption" });
s.addText("ESP32 alert: push notification and live page with one instruction, four colour tiles (heart, shaking, muscle, brain) and escalation at 2 and 5 min. Tested on an emulated board; real-phone test is next.", { x: 6.9, y: 5.6, w: 5.8, h: 1.2, fontSize: 13, color: C.text1, margin: 0, valign: "top", isTextBox: true, objectName: "Alert caption" });
s.addNotes("The dashboard shows the chip at work; the LED and buzzer fire during the seizure. The ESP32 forwards the alarm to the doctor's phone with the measured signs and one clear instruction.");

// ---------------------------------------------------------------- 14 Conclusion
pres.addSection({ title: "Conclusion" });
s = pres.addSlide({ masterName: "SECTION_DARK", sectionTitle: "Conclusion" });
s.addText("Conclusions and future work", { placeholder: "title" });
const concl = [
  "A seizure detector built from 50 FPGA lookup tables; the whole detector fits in 1,202 LUTs with no multipliers",
  "Test event-F1 0.248 at 0.8 false alarms per day; more seizures than ChronoNet at equal false alarms",
  "A self-test that detects every decision-changing fault, verified fault by fault on the board",
  "Complete system on the KV260: 9 of 9 board tests, live demo, LED, buzzer and ESP32 doctor alert",
];
const future = [
  "Test the ESP32 alert with a real phone",
  "Per-patient learning from doctor feedback, with a new self-test for every update",
  "Wearable prototype on a small low-power FPGA",
  "Paper submission (EMBC 2027)",
];
s.addText("What we achieved", { x: 0.6, y: 1.4, w: 7.0, h: 0.5, fontSize: 20, bold: true, color: C.accent1, margin: 0, isTextBox: true, objectName: "Achieved heading" });
s.addText(concl.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < concl.length - 1, paraSpaceAfter: 10 } })), { x: 0.6, y: 2.0, w: 7.0, h: 4.6, fontSize: 16, color: C.background1, margin: 0, valign: "top", isTextBox: true, objectName: "Achieved list" });
card(s, 8.2, 1.4, 4.5, 5.2, "Future card", true);
s.addText("Future work", { x: 8.5, y: 1.6, w: 3.9, h: 0.5, fontSize: 20, bold: true, color: C.background1, margin: 0, isTextBox: true, objectName: "Future heading" });
s.addText(future.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < future.length - 1, paraSpaceAfter: 10 } })), { x: 8.5, y: 2.2, w: 3.9, h: 4.2, fontSize: 16, color: C.background1, margin: 0, valign: "top", isTextBox: true, objectName: "Future list" });
s.addText("Limitation: at the default point the detector finds about one seizure in four; per-patient learning targets this.", { x: 0.6, y: 6.3, w: 7.0, h: 0.6, fontSize: 13, italic: true, color: C.accent6, margin: 0, isTextBox: true, objectName: "Limitation" });
s.addNotes("Summarise the four achievements, state the main limitation honestly, and list the next steps.");

// ---------------------------------------------------------------- 15 Thank you
s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Conclusion" });
s.addText("Thank you", { placeholder: "title" });
s.addText("Questions? We can show the live demo on the board.", { placeholder: "body" });
s.addShape(pres.shapes.OVAL, { x: 10.3, y: 2.2, w: 2.4, h: 2.4, fill: { color: C.background1 }, line: { color: C.background1 }, objectName: "Logo backdrop" });
img(s, "nitw_logo.png", 10.85, 2.55, 1.3, 1.3 * 972 / 828, "NIT Warangal logo", "NITW logo");
s.addNotes("Thank the panel and offer the live demo.");

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
