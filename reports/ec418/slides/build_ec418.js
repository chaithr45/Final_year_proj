// SeizeLUT EC418 presentation, in the course template's style (PulseScreen deck)
const pptxgen = require("pptxgenjs");
const path = require("path");
const fs = require("fs");
const { applyTheme } = require(process.env.APPLY_THEME);

const FIG = "/home/user/Final_year_proj/reports/ec418/figures/";
const HERE = __dirname;
const OUT = path.join(HERE, "SeizeLUT_EC418_Presentation.pptx");
const REFS = JSON.parse(fs.readFileSync(path.join(HERE, "refs.json"), "utf8"));

const THEME = {
  name: "SeizeLUT EC418",
  headFontFace: "Inter",
  bodyFontFace: "Inter",
  colors: {
    dk1: "1E2733", lt1: "FFFFFF", dk2: "1F3A5F", lt2: "F4F6F9",
    accent1: "C04E1C", accent2: "D9622B", accent3: "5B6675", accent4: "3A4554",
    accent5: "D5DAE1", accent6: "FBEDE5", hlink: "1F3A5F", folHlink: "5B6675",
  },
};
// hex copies for options that take hex only
const HX = { navy: "1F3A5F", ink: "3A4554", grey: "5B6675", orange: "C04E1C", orange2: "D9622B", line: "D5DAE1", panel: "F4F6F9", peach: "FBEDE5", dark: "1E2733" };

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "Akshara Bonam, Sai Chaithr, Sowjanya";
pres.title = "A Self-Testing Multimodal FPGA-Based Seizure Detection System for Tele-monitoring";
pres.theme = { headFontFace: "Inter", bodyFontFace: "Inter" };
const C = pres.SchemeColor;
const NAVY = C.text2, INK = C.accent4, GREY = C.accent3, OR = C.accent1, OR2 = C.accent2, LINE = C.accent5, PANEL = C.background2, PEACH = C.accent6;

const X0 = 0.72, W = 11.89;

pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.background1 },
  objects: [
    { line: { x: X0, y: 6.76, w: W, h: 0, line: { color: LINE, width: 0.75 } } },
    { placeholder: { options: { name: "title", type: "title", x: X0, y: 0.92, w: W, h: 0.54, fontSize: 28, bold: true, color: NAVY, valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: 12.11, y: 6.83, w: 0.5, h: 0.26, fontSize: 12, color: GREY, align: "right" },
});
pres.defineSlideMaster({ title: "PLAIN", background: { color: C.background1 }, objects: [] });

let pageNo = 0;
function content(section, eyebrow, title, sub, tagline, notes) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  s.addText(eyebrow, { x: X0, y: 0.61, w: W, h: 0.26, fontSize: 12, bold: true, color: OR, charSpacing: 1, margin: 0, isTextBox: true, objectName: "Eyebrow" });
  s.addText([{ text: title, options: { bold: true } }, { text: "  ·  " + sub, options: { bold: false } }], { placeholder: "title" });
  if (tagline) s.addText(tagline, { x: X0, y: 1.52, w: W, h: 0.35, fontSize: 15, color: GREY, margin: 0, isTextBox: true, objectName: "Tagline" });
  if (notes) s.addNotes(notes);
  return s;
}
function txt(s, text, o) {
  s.addText(text, Object.assign({ margin: 0, isTextBox: true, color: INK, fontSize: 14, valign: "top" }, o));
}
function rule(s, x, y, w, color, name) {
  s.addShape(pres.shapes.LINE, { x, y, w, h: 0, line: { color, width: 1.5 }, objectName: name });
}
function stat(s, x, y, w, num, label, hot, name) {
  rule(s, x, y, w, hot ? OR2 : NAVY, name + " rule");
  txt(s, num, { x, y: y + 0.12, w, h: 0.7, fontSize: 32, bold: true, color: hot ? OR : NAVY, valign: "middle", objectName: name + " number" });
  txt(s, label, { x, y: y + 0.9, w, h: 0.75, fontSize: 13, color: GREY, objectName: name + " label" });
}
function callout(s, y, label, text, h, name) {
  s.addShape(pres.shapes.RECTANGLE, { x: X0, y, w: W, h: h || 0.62, fill: { color: PEACH }, line: { color: PEACH }, objectName: name + " box" });
  s.addText([{ text: label + "  ", options: { bold: true, color: OR } }, { text, options: { color: HX.dark } }], { x: X0 + 0.25, y, w: W - 0.5, h: h || 0.62, fontSize: 14, valign: "middle", margin: 0, isTextBox: true, objectName: name + " text" });
}
function panelNote(s, y, label, text, h, name) {
  s.addShape(pres.shapes.RECTANGLE, { x: X0, y, w: W, h: h || 0.55, fill: { color: PANEL }, line: { color: PANEL }, objectName: name + " box" });
  s.addShape(pres.shapes.LINE, { x: X0 + 0.03, y, w: 0, h: h || 0.55, line: { color: OR2, width: 3 }, objectName: name + " mark" });
  s.addText([{ text: label + "  ", options: { bold: true, color: OR } }, { text, options: { bold: true, color: HX.dark } }], { x: X0 + 0.3, y, w: W - 0.5, h: h || 0.55, fontSize: 14, valign: "middle", margin: 0, isTextBox: true, objectName: name + " text" });
}
function table(s, rows, o) {
  const head = rows[0].map((t) => ({ text: t, options: { bold: true, color: NAVY, border: [{ type: "none" }, { type: "none" }, { pt: 1, color: HX.navy }, { type: "none" }] } }));
  const body = rows.slice(1).map((r) => r.map((t, j) => ({ text: t, options: { bold: j === 0 && o.boldFirst !== false, color: j === 0 && o.boldFirst !== false ? NAVY : INK, border: [{ type: "none" }, { type: "none" }, { pt: 0.75, color: HX.line }, { type: "none" }] } })));
  s.addTable([head, ...body], Object.assign({ fontSize: 12, margin: [3, 5, 3, 5], valign: "middle" }, o, { boldFirst: undefined }));
}
function numRows(s, items, y0, step, name) {
  items.forEach((it, i) => {
    const y = y0 + i * step;
    txt(s, String(i + 1).padStart(2, "0"), { x: X0, y, w: 0.6, h: step - 0.1, fontSize: 17, bold: true, color: OR, valign: "middle", objectName: name + " number " + (i + 1) });
    txt(s, it[0], { x: X0 + 0.75, y, w: 3.2, h: step - 0.1, fontSize: 15, bold: true, color: NAVY, valign: "middle", objectName: name + " title " + (i + 1) });
    txt(s, it[1], { x: X0 + 4.2, y, w: 7.6, h: step - 0.1, fontSize: 13, color: INK, valign: "middle", objectName: name + " text " + (i + 1) });
    rule(s, X0, y + step - 0.06, W, LINE, name + " line " + (i + 1));
  });
}
function img(s, file, x, y, w, h, alt, name) {
  s.addImage({ path: file.startsWith("/") ? file : FIG + file, x, y, w, h, altText: alt, objectName: name });
}
function fit(s, file, pw, ph, bx, by, bw, bh, alt, name) {
  const r = Math.min(bw / pw, bh / ph), w = pw * r, h = ph * r;
  img(s, file, bx + (bw - w) / 2, by + (bh - h) / 2, w, h, alt, name);
}
function bar(s, labels, values, colors, o) {
  s.addChart(pres.charts.BAR, [{ name: o.series || "Value", labels, values }], Object.assign({
    barDir: "col", varyColors: true, chartColors: colors, showValue: true, dataLabelPosition: "outEnd",
    dataLabelFontSize: 13, dataLabelColor: HX.dark, dataLabelFontFace: "+mn-lt", dataLabelFontBold: true,
    catAxisLabelColor: HX.grey, valAxisLabelColor: HX.grey, catAxisLabelFontSize: 12, valAxisLabelFontSize: 10,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", valGridLine: { color: "E6E9EE", size: 0.5 },
    catGridLine: { style: "none" }, showLegend: false, showTitle: true, titleFontSize: 13, titleColor: HX.navy,
    titleFontFace: "+mn-lt", barGapWidthPct: 60,
  }, o));
}

// ================================================================ 1 Title
pres.addSection({ title: "Introduction" });
let s = pres.addSlide({ masterName: "PLAIN", sectionTitle: "Introduction" });
img(s, "nitw_logo.png", X0, 0.45, 0.6, 0.6 * 972 / 828, "NIT Warangal logo", "NITW logo");
txt(s, "NATIONAL INSTITUTE OF TECHNOLOGY WARANGAL", { x: 1.55, y: 0.5, w: 7, h: 0.3, fontSize: 14, bold: true, color: NAVY, objectName: "Institute" });
txt(s, "Department of Electronics and Communication Engineering", { x: 1.55, y: 0.82, w: 7, h: 0.3, fontSize: 14, color: GREY, objectName: "Department" });
txt(s, "SeizeLUT", { x: X0, y: 1.55, w: 7.5, h: 0.8, fontSize: 44, bold: true, color: NAVY, valign: "middle", objectName: "Project name" });
txt(s, "A Self-Testing Multimodal FPGA-Based Seizure Detection System for Tele-monitoring", { x: X0, y: 2.45, w: 7.3, h: 0.8, fontSize: 22, bold: true, color: NAVY, objectName: "Project title" });
txt(s, "EC418 · BISP Course Project   November 2026", { x: X0, y: 3.5, w: 7, h: 0.3, fontSize: 14, color: GREY, objectName: "Course" });
txt(s, "PRESENTED BY", { x: X0, y: 4.15, w: 4, h: 0.26, fontSize: 12, bold: true, color: OR, charSpacing: 1, objectName: "Presented label" });
txt(s, [
  { text: "Akshara Bonam  ", options: { bold: true, color: HX.dark } }, { text: "23ECB0A11", options: { color: HX.ink, breakLine: true } },
  { text: "Sai Chaithr  ", options: { bold: true, color: HX.dark } }, { text: "23ECB0A20", options: { color: HX.ink, breakLine: true } },
  { text: "Sowjanya  ", options: { bold: true, color: HX.dark } }, { text: "23ECB0A22", options: { color: HX.ink } },
], { x: X0, y: 4.5, w: 4.3, h: 1.1, fontSize: 14, paraSpaceAfter: 4, objectName: "Team" });
txt(s, "UNDER THE GUIDANCE OF", { x: 5.4, y: 4.15, w: 3, h: 0.26, fontSize: 12, bold: true, color: OR, charSpacing: 1, objectName: "Guide label" });
txt(s, [{ text: "Prof. V Rama", options: { bold: true, color: HX.dark, breakLine: true } }, { text: "Associate Professor, ECE", options: { color: HX.ink } }], { x: 5.4, y: 4.65, w: 3, h: 0.7, fontSize: 14, paraSpaceAfter: 4, objectName: "Guide" });
fit(s, "dashboard_rehearsal.png", 1440, 900, 8.55, 1.5, 4.06, 3.9, "Live dashboard of the detector showing signals, LUT votes and the alarm", "Dashboard image");
s.addShape(pres.shapes.LINE, { x: X0, y: 6.76, w: W, h: 0, line: { color: LINE, width: 0.75 }, objectName: "Footer line" });
txt(s, "1", { x: 12.11, y: 6.83, w: 0.5, h: 0.26, fontSize: 12, color: GREY, align: "right", objectName: "Page number" });
s.addNotes("Introduce the team and the one-line idea: a seizure detector built from the FPGA's own lookup tables, which tests itself and tells a doctor what to do.");

// ================================================================ 2 Index
s = content("Introduction", "CONTENTS", "Index", "What This Presentation Covers", null, "Walk through the five parts of the talk.");
const cols = [
  ["01", "Introduction", [["Problem Statement", "3"], ["Objectives", "4"], ["Literature Survey", "5–7"]]],
  ["02", "System Design", [["How It Works", "8"], ["System Architecture", "9"], ["Hardware Setup", "10"], ["Dataset", "11"]]],
  ["03", "Methodology", [["Signal Chain", "12"], ["Features and LUT Network", "13"], ["Evaluation Protocol", "14"], ["Classifier in Hardware", "15"], ["Self-Test Design", "16"]]],
  ["04", "Results", [["Verification", "17"], ["Test Patients", "18"], ["Base Paper", "19–20"], ["FPGA on Kria KV260", "21–23"], ["Live Demonstration", "24–25"]]],
];
cols.forEach((c, i) => {
  const x = X0 + i * 3.07, w = 2.75;
  txt(s, c[0], { x, y: 1.75, w, h: 0.25, fontSize: 12, bold: true, color: OR, objectName: "Index number " + (i + 1) });
  txt(s, c[1], { x, y: 2.0, w, h: 0.35, fontSize: 16, bold: true, color: NAVY, objectName: "Index heading " + (i + 1) });
  rule(s, x, 2.42, w, NAVY, "Index rule " + (i + 1));
  c[2].forEach((r, j) => {
    const y = 2.55 + j * 0.52;
    txt(s, r[0], { x, y, w: w - 0.6, h: 0.35, fontSize: 13, color: INK, valign: "middle", objectName: `Index item ${i + 1}.${j + 1}` });
    txt(s, r[1], { x: x + w - 0.6, y, w: 0.6, h: 0.35, fontSize: 13, bold: true, color: NAVY, align: "right", valign: "middle", objectName: `Index page ${i + 1}.${j + 1}` });
    rule(s, x, y + 0.44, w, LINE, `Index line ${i + 1}.${j + 1}`);
  });
});
s.addShape(pres.shapes.RECTANGLE, { x: X0, y: 5.5, w: W, h: 0.8, fill: { color: PANEL }, line: { color: PANEL }, objectName: "Index band" });
[["05", "Limitations", "26", 1.0], ["06", "Conclusion and Future Work", "27", 4.6], ["", "References", "28–29", 9.4]].forEach((b, i) => {
  txt(s, [{ text: b[0] ? b[0] + "  " : "", options: { color: HX.orange, bold: true } }, { text: b[1], options: { color: HX.navy, bold: true } }, { text: "   " + b[2], options: { color: HX.grey } }], { x: X0 + b[3] - 0.7, y: 5.5, w: 4.4, h: 0.8, fontSize: 16, valign: "middle", objectName: "Index band item " + (i + 1) });
});

// ================================================================ 3 Problem statement
s = content("Introduction", "SEIZELUT · MOTIVATION", "Problem Statement", "Unseen Seizures, Silent Failures", "Many seizures go unnoticed, and a broken detector looks exactly like a quiet night",
  "Epilepsy affected about 45.9 million people in 2016 [1]. Patients under-report their own seizures [2]. Wearables are recommended today only for tonic-clonic seizures [4].");
s.addShape(pres.shapes.RECTANGLE, { x: X0, y: 2.15, w: W, h: 1.42, fill: { color: PANEL }, line: { color: PANEL }, objectName: "Question box" });
s.addShape(pres.shapes.LINE, { x: X0 + 0.03, y: 2.15, w: 0, h: 1.42, line: { color: OR2, width: 3 }, objectName: "Question mark" });
txt(s, "RESEARCH QUESTION", { x: 1.03, y: 2.35, w: 11.3, h: 0.26, fontSize: 12, bold: true, color: OR, charSpacing: 1, objectName: "Question label" });
txt(s, "Can a network built only from FPGA lookup tables detect seizures from wearable signals in unseen patients, test its own hardware, and alert a doctor?", { x: 1.03, y: 2.63, w: 11.3, h: 0.78, fontSize: 18, bold: true, color: NAVY, objectName: "Question" });
[["Missed seizures", "45.9 million people had epilepsy in 2016 [1]; patients often miss their own seizures, so diaries undercount them [2].", false],
 ["Too many false alarms", "Wearables are recommended only for tonic-clonic seizures [4]; for focal seizures false alarms are the main obstacle [5].", false],
 ["Silent failure", "A fault in the classifier hardware turns into missed seizures or false alarms, and nobody notices.", true]].forEach((c, i) => {
  const x = X0 + i * 4.075;
  rule(s, x, 3.92, 3.74, c[2] ? OR2 : NAVY, "Column rule " + (i + 1));
  txt(s, c[0], { x, y: 4.09, w: 3.8, h: 0.37, fontSize: 18, bold: true, color: c[2] ? OR : NAVY, valign: "middle", objectName: "Column title " + (i + 1) });
  txt(s, c[1], { x, y: 4.53, w: 3.74, h: 0.97, fontSize: 14, objectName: "Column text " + (i + 1) });
});
callout(s, 5.62, "OUR AIM", "A multiplier-free detector in a few hundred FPGA lookup tables that checks itself and tells the doctor what to do.", 0.9, "Aim");

// ================================================================ 4 Objectives
s = content("Introduction", "SEIZELUT · MOTIVATION", "Objectives", "What the Project Set Out to Do", "Seven goals that take wearable signals to a self-tested FPGA alarm and a doctor's phone",
  "Each objective was completed; the ESP32 alert is tested in emulation and the real-phone test is pending.");
numRows(s, [
  ["Audit and baseline", "Audit the SeizeIT2 dataset and reproduce its published ChronoNet baseline."],
  ["Integer front end", "Bit-exact multimodal features with no multiplier and no division."],
  ["Compare and extend", "LUT-native, tree and multiplier-based models on accuracy and hardware cost; distillation, missing sensors, post-ictal check."],
  ["One final test", "Evaluate the frozen design once on the 29 held-out test patients."],
  ["Self-test", "Analyse every single hardware fault and detect every fault that can change a decision."],
  ["Whole detector on the FPGA", "Front end and classifier in the fabric of the AMD Kria KV260, verified on the board."],
  ["Alarm and doctor alert", "Alarm LED and buzzer on a breadboard; push notification through an ESP32."],
], 1.95, 0.66, "Objective");

// ================================================================ 5 Literature 1
s = content("Introduction", "SEIZELUT · LITERATURE SURVEY   ·   1 OF 3", "Literature Survey", "Wearable Seizure Detection", "Behind-the-ear EEG works, extra sensors cut false alarms, but published detectors are large software models",
  "Results are as reported in the cited papers.");
table(s, [
  ["Ref.", "Work", "What it showed", "What we take from it"],
  ["[6]", "Vandecasteele et al., 2020: behind-the-ear EEG", "64.1 % of focal seizures, 2.8 false alarms per 24 h, patient-independent", "Two discreet EEG channels"],
  ["[7]", "Vandecasteele et al., 2021: bte-EEG + ECG", "ECG adds 8–11 % sensitivity", "Fuse the heart signal"],
  ["[18]", "Zhang et al., 2024: EEG + EMG + motion", "90.9 %, 0.1 false alarms per 24 h, tonic-clonic seizures", "EMG and motion remove false alarms"],
  ["[8], [5]", "Bhagubai et al., 2025; Swinnen et al., 2026: SeizeIT2", "125 patients released; a 192-adult validation reached precision 0.004", "Our dataset; false alarms are the problem"],
  ["[27], [26]", "ChronoNet, 2019; Huang et al., 2023", "CNN + GRU; trained on SeizeIT1 it reached 15.2 % on SeizeIT2", "The published baseline we reproduce"],
], { x: X0, y: 2.05, w: W, colW: [1.1, 3.6, 4.2, 2.99] });
panelNote(s, 5.75, "RESEARCH GAP", "Hardware seizure detectors use EEG alone, and none builds its classifier from FPGA lookup tables.", 0.55, "Gap");

// ================================================================ 6 Literature 2
s = content("Introduction", "SEIZELUT · LITERATURE SURVEY   ·   2 OF 3", "Literature Survey", "LUT-Native Networks", "Networks made of lookup tables are tiny and fast, but were never used for seizures",
  "The DWN is the model family we build on; TreeLUT and logic-gate networks are compared in our results.");
table(s, [
  ["Ref.", "Work", "What it showed", "What we take from it"],
  ["[9]", "Bacellar et al., 2024: Differentiable Weightless Networks", "LUT contents and input mapping trained by gradient descent; runs on FPGA and MCU", "Our classifier"],
  ["[10], [11]", "Logic-gate networks, 2022; LogicNets, 2020", "Learned 2-input gates; sparse LUT networks with < 15 ns latency", "Compared alternatives"],
  ["[55]", "TreeLUT, 2025: quantised boosted trees in LUTs", "4–101× lower area-delay than neural networks", "Compared baseline"],
  ["[56]", "Mecik and Kumm, 2025: DWN on FPGA", "The thermometer encoder can cost up to 3.2× the LUTs", "We count every comparator"],
  ["[69]", "Busia et al., 2025: spiking network on an iCE40 FPGA", "4.55 nJ per inference, 0.3 false alarms per hour, EEG only", "Closest FPGA detector"],
  ["[59]", "de Aguiar et al., 2015: WiSARD", "Seizure anticipation in 4 patients, accuracy only", "Only earlier weightless seizure work"],
], { x: X0, y: 2.05, w: W, colW: [1.1, 3.9, 4.2, 2.69] });
panelNote(s, 5.75, "RESEARCH GAP", "No LUT-native seizure detector exists, and LUT networks were never tested on multimodal biosignals.", 0.55, "Gap");

// ================================================================ 6b Literature 3
s = content("Introduction", "SEIZELUT · LITERATURE SURVEY   ·   3 OF 3", "Literature Survey", "Hardware Seizure Detectors", "Chips, FPGAs and microcontrollers detect seizures at nJ to mJ per decision, almost always from EEG alone",
  "Results are as reported; units differ between papers, so the numbers are not directly comparable.");
table(s, [
  ["Ref.", "Work", "What it showed", "Limitation for our problem"],
  ["[60]", "Verma et al., 2010: EEG acquisition ASIC", "On-chip spectral features at 9 µJ per feature vector", "Classifier off-chip"],
  ["[61], [62]", "Bin Altaf et al., 2015–16: SVM ASICs", "2.73 and 1.83 µJ per classification", "Trained per patient, EEG only"],
  ["[63]", "Shoaran et al., 2018: boosted-tree ASIC", "41.2 nJ per classification on intracranial EEG", "Implant, not wearable"],
  ["[65]", "Wang et al., 2018: STFT + SVM on a Zynq FPGA", "98.4 %, 0.356 false detections per hour, 380 mW", "Per patient, EEG only"],
  ["[69]", "Busia et al., 2025: spiking network on FPGA", "4.55 nJ per inference, 0.3 false positives per hour", "EEG only, not LUT-native"],
  ["[70], [71]", "e-Glass, 2018; EEGformer, 2024: microcontrollers", "2.71 days per charge; 73 % at 0.15 false positives per hour", "Multipliers, EEG only"],
], { x: X0, y: 2.05, w: W, colW: [1.1, 3.9, 4.2, 2.69] });
panelNote(s, 5.75, "RESEARCH GAP", "No surveyed detector builds its classifier from FPGA lookup tables or checks its classifier for hardware faults in use.", 0.55, "Gap");

// ================================================================ 7 How it works
pres.addSection({ title: "System Design" });
s = content("System Design", "SEIZELUT · SYSTEM", "How It Works", "Three Steps", "Signals in, alarm and doctor alert out, every second",
  "Every second the board takes the last two seconds of signal, computes features, decides, and updates the alarm.");
[["Sense", "Behind-the-ear EEG, ECG, EMG and motion arrive second by second (recorded test-patient signals on the board)."],
 ["Detect in the FPGA", "A shift-add engine computes 38 features; 146 comparators and 50 lookup tables vote; 10 high seconds raise the alarm."],
 ["Alert", "The red LED and buzzer turn on, and an ESP32 pushes a notification with one clear instruction to the doctor's phone."]].forEach((c, i) => {
  const x = X0 + i * 4.075;
  rule(s, x, 2.15, 3.74, i === 2 ? OR2 : NAVY, "Step rule " + (i + 1));
  txt(s, String(i + 1).padStart(2, "0"), { x, y: 2.3, w: 1, h: 0.3, fontSize: 14, bold: true, color: OR, objectName: "Step number " + (i + 1) });
  txt(s, c[0], { x, y: 2.62, w: 3.74, h: 0.4, fontSize: 18, bold: true, color: i === 2 ? OR : NAVY, valign: "middle", objectName: "Step title " + (i + 1) });
  txt(s, c[1], { x, y: 3.1, w: 3.74, h: 1.1, fontSize: 14, objectName: "Step text " + (i + 1) });
});
fit(s, "dashboard_rehearsal.png", 1440, 900, X0, 4.25, 5.6, 2.35, "Live dashboard", "Dashboard image");
fit(s, "alert_page.png", 2370, 1992, 7.0, 4.25, 5.6, 2.35, "Doctor alert page on a phone", "Alert image");

// ================================================================ 8 System architecture
s = content("System Design", "SEIZELUT · SYSTEM", "System Architecture", "Block Diagram", "The Arm cores only move raw samples; the whole detector runs in the FPGA fabric",
  "The ESP32 also has a wire from the FPGA's alarm pin, so the alert works even if the board's software stops.");
function blk(x, y, w, h, title, body, hot, name) {
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: hot ? PEACH : C.background1 }, line: { color: hot ? OR2 : NAVY, width: 1 }, objectName: name + " box" });
  txt(s, title, { x: x + 0.12, y: y + 0.08, w: w - 0.24, h: 0.3, fontSize: 13, bold: true, color: hot ? OR : NAVY, objectName: name + " title" });
  txt(s, body, { x: x + 0.12, y: y + 0.4, w: w - 0.24, h: h - 0.45, fontSize: 11, color: INK, objectName: name + " text" });
}
blk(X0, 2.2, 2.4, 1.2, "Signals", "Raw EEG, ECG, EMG at 256 Hz; motion at 25 Hz", false, "Signals");
s.addShape(pres.shapes.RECTANGLE, { x: 3.45, y: 2.0, w: 6.3, h: 4.4, fill: { color: PANEL }, line: { color: LINE, width: 1 }, objectName: "KV260 frame" });
txt(s, "AMD Kria KV260", { x: 3.6, y: 2.05, w: 4, h: 0.3, fontSize: 13, bold: true, color: NAVY, objectName: "KV260 label" });
blk(3.65, 2.45, 2.5, 0.95, "Arm cores (PYNQ)", "Write raw samples; read results", false, "Arm");
blk(6.4, 2.45, 3.15, 0.95, "Feature engine", "Shift-add microcode: 38 features, no multiplier", false, "Engine");
blk(6.4, 3.6, 3.15, 1.05, "Classifier", "146 comparators → 50 LUT6 → popcount score → 10-of-10 alarm", true, "Classifier");
blk(3.65, 3.6, 2.5, 1.05, "Self-test, faults", "1,024 vectors in 10.3 µs; any fault on demand", false, "BIST");
blk(3.65, 4.85, 5.9, 1.3, "PMOD pins", "Alarm LED (B1), buzzer through a BC547 (B2), alarm wire to the ESP32", false, "PMOD");
blk(10.0, 2.2, 2.6, 1.2, "Laptop", "Live dashboard in the browser", false, "Laptop");
blk(10.0, 3.6, 2.6, 1.3, "ESP32", "USB serial messages and alarm wire; push through ntfy", true, "ESP32");
blk(10.0, 5.1, 2.6, 1.05, "Doctor's phone", "Notification, live page, “On my way”", false, "Phone");
[[3.12, 2.8, 0.33], [6.15, 2.92, 0.25], [9.55, 2.8, 0.45], [9.55, 4.2, 0.45]].forEach((a, i) => s.addShape(pres.shapes.LINE, { x: a[0], y: a[1], w: a[2], h: 0, line: { color: HX.grey, width: 1.25, endArrowType: "triangle" }, objectName: "Arrow " + (i + 1) }));
s.addShape(pres.shapes.LINE, { x: 7.97, y: 3.4, w: 0, h: 0.2, line: { color: HX.grey, width: 1.25, endArrowType: "triangle" }, objectName: "Arrow 5" });
s.addShape(pres.shapes.LINE, { x: 11.3, y: 4.9, w: 0, h: 0.2, line: { color: HX.grey, width: 1.25, endArrowType: "triangle" }, objectName: "Arrow 6" });

// ================================================================ 9 Hardware setup
s = content("System Design", "SEIZELUT · SYSTEM", "Hardware", "Components and Setup", "One FPGA board, a few parts on a breadboard, and a phone",
  "The board replays recorded test-patient signals second by second, exactly as it would process live sensors.");
table(s, [
  ["Component", "Part", "Function"],
  ["FPGA board", "AMD Kria KV260 (Zynq UltraScale+ XCK26), Kria-PYNQ", "Feature engine, classifier, self-test"],
  ["Alarm LED", "Red LED, 220 Ω, PMOD B1", "On while the alarm is on"],
  ["Buzzer", "Buzzer via BC547, 1 kΩ base, PMOD B2", "Sounds while the alarm is on"],
  ["Alert module", "ESP32 Dev Module, USB serial + GPIO 27", "Push notification and live page"],
  ["Phone", "iPhone, ntfy app, personal hotspot", "Alert and “On my way” reply"],
  ["Laptop", "Web browser", "Live dashboard"],
], { x: X0, y: 2.05, w: 7.6, colW: [1.6, 3.4, 2.6] });
stat(s, 8.75, 2.15, 3.86, "1,202 LUTs", "for the whole detector (front end + classifier), no multiplier", true, "Stat LUTs");
stat(s, 8.75, 4.0, 3.86, "3.2 %", "of the KV260 device for the full design (3,796 LUTs, 0 DSP)", false, "Stat device");

// ================================================================ 10 Dataset
s = content("System Design", "SEIZELUT · DATA", "Dataset", "SeizeIT2 (OpenNeuro ds005873)", "125 patients with focal epilepsy, wearable recordings, seizures marked on hospital video-EEG [8]",
  "We kept the official split. Every design choice was made on the 96 training patients; the 29 test patients were scored once at the end.");
[["125", "patients"], ["11,626 h", "of EEG recorded"], ["883", "seizures (702 train, 181 test)"], ["0.123 %", "of the time is seizure"]].forEach((d, i) => stat(s, X0 + i * 3.07, 2.05, 2.75, d[0], d[1], i === 3, "Dataset stat " + (i + 1)));
fit(s, "hours_and_seizures_per_patient.png", 1200, 480, X0, 3.8, 7.2, 2.85, "Hours recorded and seizures per patient", "Hours chart");
table(s, [["Signal", "Channels", "Rate"], ["bte-EEG", "2", "256 Hz"], ["ECG", "1", "256 Hz"], ["EMG", "1", "256 Hz"], ["Motion", "acc. + gyro.", "25 Hz"]], { x: 8.3, y: 3.95, w: 4.31, colW: [1.4, 1.6, 1.31] });

// ================================================================ 11 Signal chain
pres.addSection({ title: "Methodology" });
s = content("Methodology", "SEIZELUT · METHOD", "Methodology", "Signal Chain", "Every second, two seconds of signal become one alarm decision, with only shifts and additions",
  "The same integer front end exists in Python, in C and in the FPGA, and all three give the same numbers for every window.");
const chain = [["Raw signals", "256 Hz / 25 Hz"], ["Shift-add filters", "no multiplier"], ["38 features", "integer"], ["146 thresholds", "comparator bits"], ["50 LUT6 vote", "popcount score"], ["Alarm", "10 of 10 s"]];
chain.forEach((c, i) => {
  const x = X0 + i * 2.0, w = 1.75;
  s.addShape(pres.shapes.RECTANGLE, { x, y: 2.2, w, h: 1.3, fill: { color: i === 5 ? PEACH : PANEL }, line: { color: i === 5 ? PEACH : PANEL }, objectName: "Chain box " + (i + 1) });
  txt(s, String(i + 1), { x: x + 0.15, y: 2.3, w: 0.5, h: 0.3, fontSize: 14, bold: true, color: OR, objectName: "Chain number " + (i + 1) });
  txt(s, c[0], { x: x + 0.15, y: 2.62, w: w - 0.3, h: 0.45, fontSize: 14, bold: true, color: i === 5 ? OR : NAVY, objectName: "Chain title " + (i + 1) });
  txt(s, c[1], { x: x + 0.15, y: 3.07, w: w - 0.3, h: 0.3, fontSize: 11, color: GREY, objectName: "Chain text " + (i + 1) });
  if (i < 5) s.addShape(pres.shapes.LINE, { x: x + w + 0.02, y: 2.85, w: 0.2, h: 0, line: { color: HX.grey, width: 1.25, endArrowType: "triangle" }, objectName: "Chain arrow " + (i + 1) });
});
[["INTEGER ARITHMETIC", "Every filter coefficient is a sum of a few signed powers of two, with error feedback; heart rate uses log₂(RR), so there is no division."],
 ["MISSING SENSORS", "A presence bit per sensor tells the network when ECG, EMG or motion is missing; modality dropout keeps it working without them."]].forEach((c, i) => {
  const x = X0 + i * 6.08;
  rule(s, x, 4.0, 5.8, i ? OR2 : NAVY, "Note rule " + (i + 1));
  txt(s, c[0], { x, y: 4.15, w: 5.8, h: 0.26, fontSize: 12, bold: true, color: OR, charSpacing: 1, objectName: "Note label " + (i + 1) });
  txt(s, c[1], { x, y: 4.5, w: 5.8, h: 1.0, fontSize: 14, objectName: "Note text " + (i + 1) });
});
callout(s, 5.75, "RESULT", "Integer features track their floating-point twin (median correlation 0.9965) with the same accuracy (AUROC 0.736 vs 0.735).", 0.62, "Result");

// ================================================================ 12 Features and LUT network
s = content("Methodology", "SEIZELUT · METHOD", "Methodology", "Features and the LUT Network", "Each neuron is a 6-input truth table, exactly one FPGA lookup table [9]",
  "Distillation from a LightGBM teacher cut the false alarms on the training patients from 2.4 to 0.9 per day.");
table(s, [
  ["Group", "Count", "Features (per 2-s window)"],
  ["EEG", "84", "amplitude, line length, mobility, zero crossings, 5 band amplitudes, artefact flags"],
  ["ECG", "5", "log heart period, log RR variability, quality flag"],
  ["EMG", "8", "amplitude, line length, zero crossings, band ratio"],
  ["Motion", "16", "accelerometer and gyroscope magnitude, jerk, activity"],
  ["Presence", "4", "one bit per sensor"],
], { x: X0, y: 2.05, w: 6.9, colW: [1.2, 0.8, 4.9] });
txt(s, "117 features are computed; the final network reads 38 of them.", { x: X0, y: 4.85, w: 6.9, h: 0.3, fontSize: 12, color: GREY, objectName: "Feature note" });
s.addShape(pres.shapes.RECTANGLE, { x: 8.0, y: 2.05, w: 4.61, h: 4.5, fill: { color: PANEL }, line: { color: PANEL }, objectName: "DWN panel" });
txt(s, "HOW THE DWN DECIDES", { x: 8.25, y: 2.2, w: 4.2, h: 0.26, fontSize: 12, bold: true, color: OR, charSpacing: 1, objectName: "DWN label" });
[["1  Threshold", "b = [ feature > t ]: 146 learned comparators"], ["2  Look up", "each of 50 LUTs reads 6 bits and outputs its stored bit"], ["3  Count", "score = seizure votes − background votes"], ["4  Alarm", "score above threshold in 10 of the last 10 s"]].forEach((r, i) => {
  txt(s, r[0], { x: 8.25, y: 2.6 + i * 0.9, w: 4.2, h: 0.3, fontSize: 14, bold: true, color: NAVY, objectName: "DWN step " + (i + 1) });
  txt(s, r[1], { x: 8.25, y: 2.92 + i * 0.9, w: 4.2, h: 0.55, fontSize: 12, objectName: "DWN text " + (i + 1) });
});
s.addShape(pres.shapes.RECTANGLE, { x: X0, y: 5.45, w: 6.9, h: 1.0, fill: { color: PEACH }, line: { color: PEACH }, objectName: "Training box" });
s.addText([{ text: "TRAINING  ", options: { bold: true, color: HX.orange } }, { text: "Gradient descent through a relaxed lookup, then distillation from a LightGBM teacher.", options: { color: HX.dark } }], { x: X0 + 0.25, y: 5.45, w: 6.4, h: 1.0, fontSize: 14, valign: "middle", margin: 0, isTextBox: true, objectName: "Training text" });

// ================================================================ 13 Evaluation protocol
s = content("Methodology", "SEIZELUT · METHOD", "Methodology", "Evaluation Protocol", "Clinical event scoring, split by patient, with a test set opened only once",
  "SzCORE event scoring: an alarm counts if it overlaps a seizure from 30 s before to 60 s after.");
numRows(s, [
  ["Patient-wise folds", "5-fold cross-validation on the 96 training patients for every design choice."],
  ["Sealed test set", "29 test patients (sub-097 to sub-125) scored once after the freeze, 5 seeds, every access logged."],
  ["Event scoring", "SzCORE [37]: sensitivity, precision and event-F1 per patient, and false alarms per 24 h."],
  ["Operating points", "Chosen on the training folds: best event-F1, and most seizures with at most 1 false alarm per hour."],
  ["Statistics", "Paired Wilcoxon test per patient; a change is kept only if p < 0.05 in its favour."],
], 2.0, 0.78, "Protocol");
callout(s, 6.0, "WHY", "Seizures are 0.123 % of the time, so accuracy is meaningless; false alarms per day decide whether a device is used.", 0.6, "Why");

// ================================================================ 14 Classifier in hardware
s = content("Methodology", "SEIZELUT · HARDWARE", "Classifier in Hardware", "One Core in the Fabric", "The feature engine and the classifier sit behind one AXI4-Lite bus at 100 MHz",
  "After each window the core copies the engine's 38 features into the classifier and classifies them automatically.");
table(s, [
  ["Block", "What it does"],
  ["Feature engine", "40-bit adder, two 5-bit shifters, 930-word register file, 2,323-instruction program, 3 cycles per instruction"],
  ["Classifier", "146 comparators, 50 LUT6, popcount score, frozen and programmable operating points"],
  ["Self-test (BIST)", "Vector ROM and response check: 1,024 vectors in 1,028 cycles"],
  ["Fault injection", "Flip any truth-table bit or force any comparator or LUT output"],
  ["Debug read-back", "All 146 comparator bits and 50 LUT outputs of the last window"],
  ["Demo I/O", "PMOD outputs for LED, buzzer, score LEDs; debounced button"],
], { x: X0, y: 2.05, w: 7.9, colW: [1.8, 6.1] });
stat(s, 9.05, 2.15, 3.56, "3 cycles", "from features to decision (30 ns)", false, "Stat latency");
stat(s, 9.05, 4.0, 3.56, "< 1 MHz", "engine cycles needed per second of signal, a hundredth of the clock", true, "Stat engine");

// ================================================================ 15 Self-test design
s = content("Methodology", "SEIZELUT · SELF-TEST", "Self-Test", "Every Fault, Judged by Its Effect", "Because the classifier is a set of truth tables, every hardware fault can be listed and tested",
  "Each fault was applied to all 31.4 million training windows; a fault matters if it changes at least one decision.");
[["3,200", "truth-table bits that can flip (configuration upset)"], ["392", "comparator and LUT outputs stuck at 0 or 1"], ["2,890", "faults that change a decision on training data"], ["255", "selected test windows that catch all of them"]].forEach((d, i) => stat(s, X0 + i * 3.07, 2.05, 2.75, d[0], d[1], i === 3, "Fault stat " + (i + 1)));
numRows(s, [
  ["List every fault", "3,592 single faults: 3,200 bit flips + 292 comparator + 100 LUT stuck-at faults."],
  ["Measure the effect", "Simulate each fault on 8,714 hours of training data; keep the 2,890 that change a decision."],
  ["Pick test windows", "Choose training windows for coverage until every decision-relevant fault is caught."],
], 3.95, 0.72, "BIST step");
callout(s, 6.05, "ON CHIP", "1,024 vectors in 1,028 cycles = 10.3 µs, short enough to run after every one-second window.", 0.55, "On chip");

// ================================================================ 16 Verification
pres.addSection({ title: "Results" });
s = content("Results", "SEIZELUT · RESULTS", "Verification", "Software and Hardware Parity", "Every implementation gives the same numbers as the golden model, window by window",
  "Parity shows the model was carried into hardware intact; accuracy is on the next slides.");
stat(s, X0, 1.95, 3.74, "431,960", "windows replayed in Verilog and on the board: 0 mismatches", true, "Stat windows");
stat(s, X0 + 4.075, 1.95, 3.74, "3,592 / 3,592", "injected faults behave as predicted on the board", false, "Stat faults");
stat(s, X0 + 8.15, 1.95, 3.74, "9,214", "windows from raw samples through the fabric: 0 mismatches", false, "Stat fabric");
table(s, [
  ["Check", "Result"],
  ["Integer vs floating-point features", "median correlation 0.9965; artefact flags agree 99.7 %"],
  ["Verilog of the final DWN (Icarus)", "431,960 windows, 0 mismatches"],
  ["Engine program vs C front end", "all 431,960 windows equal (38 features)"],
  ["Engine RTL and whole core (Verilator)", "4,278 windows, 0 mismatches"],
  ["Core RTL regression with every fault", "863,920 checks and all 3,592 faults pass"],
], { x: X0, y: 3.85, w: W, colW: [4.4, 7.49] });

// ================================================================ 17 Test patients
s = content("Results", "SEIZELUT · RESULTS", "Results", "29 Unseen Test Patients", "Fewer than one false alarm a day, from 398 lookup tables",
  "LightGBM is more accurate but needs about 30,800 LUTs; among small multiplier-free models the DWN is the best.");
[["0.248", "event-F1 of the final DWN (± 0.016, 5 seeds)", true], ["0.8 / day", "false alarms at the default operating point", false], ["p = 0.027", "better than ChronoNet (paired Wilcoxon)", false], ["398 LUTs", "for the classifier, no DSP", false]].forEach((d, i) => stat(s, X0 + i * 3.07, 1.95, 2.75, d[0], d[1], d[2], "Test stat " + (i + 1)));
table(s, [
  ["Model", "Event-F1", "False alarms / day", "Cost"],
  ["DWN + distillation (ours)", "0.248", "0.8", "≈ 900 LUTs (estimate)"],
  ["LightGBM", "0.308", "0.6", "≈ 30.8k LUTs"],
  ["Random forest", "0.246", "0.2", "≈ 347k LUTs"],
  ["TreeLUT", "0.233", "1.0", "≈ 6.3k LUTs"],
  ["Logic-gate network", "0.191", "1.4", "≈ 7.5k LUTs"],
  ["INT8 MLP", "0.155", "1.7", "9,600 multiplications"],
  ["ChronoNet (clean)", "0.027", "106", "CNN + GRU"],
], { x: X0, y: 3.85, w: W, colW: [4.0, 2.2, 2.6, 3.09], fontSize: 11, margin: [2, 5, 2, 5] });

// ================================================================ 18 Base paper
s = content("Results", "SEIZELUT · RESULTS", "Results", "Against the Base Paper", "At the same false-alarm rate, more seizures than the deep-learning baseline",
  "ChronoNet's threshold was read from its own test curve, which favours it.");
bar(s, ["Our DWN", "ChronoNet (clean)"], [43.2, 34.8], [HX.orange2, "8A96A6"], { x: X0, y: 1.95, w: 5.6, h: 4.65, dataLabelFormatCode: "0.0", title: "Seizures detected (%) at about 1.25 false alarms per hour", valAxisMaxVal: 50, valAxisMinVal: 0, objectName: "Equal-FA chart" });
table(s, [
  ["Model", "Detected", "FA / h"],
  ["SVM, published [8]", "71.1 %", "11.0"],
  ["ChronoNet, published [8]", "84.2 %", "100.5"],
  ["ChronoNet, our clean reproduction", "67.1 %", "11.9"],
  ["Our DWN, ≤ 1 FA/h point", "43.2 %", "1.24"],
  ["Our DWN, best-F1 point", "25.5 %", "0.02"],
], { x: 6.85, y: 2.05, w: 5.76, colW: [3.36, 1.2, 1.2] });
s.addShape(pres.shapes.RECTANGLE, { x: 6.85, y: 4.6, w: 5.76, h: 1.0, fill: { color: PEACH }, line: { color: PEACH }, objectName: "Also box" });
s.addText([{ text: "ALSO  ", options: { bold: true, color: HX.orange } }, { text: "Better window ranking (AUROC 0.883 vs 0.746), with no multipliers.", options: { color: HX.dark } }], { x: 7.05, y: 4.6, w: 5.4, h: 1.0, fontSize: 14, valign: "middle", margin: 0, isTextBox: true, objectName: "Also text" });

// ================================================================ 19 Two-stage
s = content("Results", "SEIZELUT · RESULTS", "Results", "Two-Stage Detector", "A second 50-LUT network confirms each alarm 96 s later and beats the dataset paper's SVM",
  "Settings were chosen on the training patients and committed before one test evaluation. All 5 seeds were above 71.1 %.");
bar(s, ["Ours, two-stage (10.9 FA/h)", "SVM, published (11.0 FA/h)", "ChronoNet, clean (11.9 FA/h)"], [73.3, 71.1, 67.1], [HX.orange2, "8A96A6", "8A96A6"], { x: X0, y: 1.95, w: 7.2, h: 4.65, title: "Seizures detected (%) at about 11 false alarms per hour", dataLabelFormatCode: "0.0", valAxisMaxVal: 80, valAxisMinVal: 0, objectName: "Two-stage chart" });
stat(s, 8.4, 2.05, 4.21, "+2.2 points", "more seizures than the SVM at a slightly lower false-alarm rate", true, "Stat margin");
stat(s, 8.4, 3.9, 4.21, "96 s", "decision delay: suits seizure logging, not instant alarms", false, "Stat delay");

// ================================================================ 20 FPGA cost
s = content("Results", "SEIZELUT · RESULTS", "FPGA", "Hardware Cost on the Kria KV260", "The DWN is 6.7× smaller than TreeLUT and 13.2× smaller than a logic-gate network",
  "Vivado 2026.1 out of context at a 2.5-ns constraint; Yosys gives the same totals.");
bar(s, ["DWN (ours)", "TreeLUT", "Logic-gate net"], [398, 2677, 5249], [HX.orange2, "8A96A6", "8A96A6"], { x: X0, y: 1.95, w: 6.0, h: 4.65, title: "LUTs of the classifier (XCK26)", objectName: "LUT chart", dataLabelFormatCode: "#,##0" });
table(s, [
  ["Part", "Cost"],
  ["DWN classifier", "398 LUTs, 468 MHz, 17 mW"],
  ["Feature engine", "804 LUTs, 4.5 BRAM, 234 MHz"],
  ["Whole detector", "1,202 LUTs, no multiplier"],
  ["Core with test and debug", "3,356 LUTs, 13.5 BRAM"],
  ["Full design", "3,796 LUTs (3.2 %), 0 DSP"],
  ["Timing", "met at 100 MHz, slack 3.5 ns"],
], { x: 7.1, y: 2.05, w: 5.51, colW: [2.3, 3.21] });

// ================================================================ 21 Self-test coverage
s = content("Results", "SEIZELUT · RESULTS", "FPGA", "Self-Test Coverage", "The obvious test misses half of the dangerous faults; the selected windows miss none",
  "The obvious test, replaying 1,024 consecutive recorded windows, misses faults in rarely used truth-table entries.");
bar(s, ["1,024 consecutive windows", "Random windows", "255 selected windows"], [50.7, 82.2, 100.0], ["8A96A6", "8A96A6", HX.orange2], { x: X0, y: 1.95, w: 6.6, h: 4.65, title: "Decision-relevant faults detected (%)", valAxisMaxVal: 100, valAxisMinVal: 0, dataLabelFormatCode: "0.0", objectName: "Coverage chart" });
fit(s, path.join(HERE, "fault_coverage.png"), 651, 438, 7.7, 1.95, 4.91, 2.9, "Faults detected by the first m self-test vectors", "Coverage curve");
stat(s, 7.7, 5.0, 2.3, "10.3 µs", "per on-chip self-test", true, "Stat BIST");
stat(s, 10.3, 5.0, 2.31, "88 s", "all faults injected on the board", false, "Stat campaign");

// ================================================================ 22 Board tests
s = content("Results", "SEIZELUT · RESULTS", "FPGA", "Board Test Campaign", "One script, nine tests, all passing on our KV260",
  "Step 5 covers 10 exported recordings of three test patients, as a check that the board equals the software.");
table(s, [
  ["Step", "Measured on the board", "Result"],
  ["1 Identity", "core version 3, 38 features, 50 LUTs; bitstream loads in 4.4 s", "PASS"],
  ["2 Self-test", "1,024 of 1,024 vectors correct in 1,028 cycles", "PASS"],
  ["3 Latency", "3 clock cycles (30 ns)", "PASS"],
  ["4 Replay", "431,960 windows, 0 mismatches; 3.2 µs per window", "PASS"],
  ["5 Detection", "equal to simulation on 10 recordings", "reported"],
  ["6 Power", "3.069 W idle, 3.074 W with the classifier busy", "reported"],
  ["7 Front end on Arm", "0 feature and 0 output mismatches", "PASS"],
  ["8 Fault injection", "3,592 faults, 0 mismatches; all 2,890 relevant faults detected", "PASS"],
  ["9 Whole detector in fabric", "9,214 windows from raw samples, 0 mismatches; 102–124× real time", "PASS"],
], { x: X0, y: 1.95, w: W, colW: [2.8, 7.6, 1.49], fontSize: 12, margin: [2, 5, 2, 5] });

// ================================================================ 23 Live demo
s = content("Results", "SEIZELUT · RESULTS", "Work Done", "Live Demonstration", "Recorded test signals stream through the board; LED and buzzer fire during the seizure",
  "The dashboard checks on every window that the FPGA equals the software.");
fit(s, "dashboard_rehearsal.png", 1440, 900, X0, 1.95, 7.4, 4.65, "Live dashboard: signals, features, comparator bits, LUT votes, score and alarm", "Dashboard");
table(s, [
  ["PMOD pin", "Breadboard"],
  ["B1", "220 Ω → red LED; also ESP32 GPIO 27"],
  ["B2", "1 kΩ → BC547 base; collector → buzzer (−)"],
  ["3.3 V", "buzzer (+)"],
  ["GND", "ground rail, ESP32 GND"],
], { x: 8.4, y: 2.05, w: 4.21, colW: [1.1, 3.11] });
callout2(s);
function callout2(sl) {
  sl.addShape(pres.shapes.RECTANGLE, { x: 8.4, y: 4.6, w: 4.21, h: 1.9, fill: { color: PEACH }, line: { color: PEACH }, objectName: "Demo note box" });
  sl.addText([{ text: "RUN  ", options: { bold: true, color: HX.orange } }, { text: "bash demo2_components.sh --autoplay --speed 4", options: { color: HX.dark } }, { text: "   The alarm turns on about half a minute in.", options: { color: HX.ink, breakLine: false } }], { x: 8.6, y: 4.7, w: 3.85, h: 1.7, fontSize: 13, valign: "middle", margin: 0, isTextBox: true, objectName: "Demo note text" });
}

// ================================================================ 24 Doctor alert
s = content("Results", "SEIZELUT · RESULTS", "Work Done", "Doctor Alert with an ESP32", "Readable in two seconds: where, what to do, and the four key signs",
  "Tested on an emulated board through a virtual serial port; the test on the ESP32 with a real phone is next.");
fit(s, "alert_page.png", 2370, 1992, X0, 1.95, 5.6, 4.65, "Doctor page at a new seizure and in an emergency after 5 minutes", "Alert page");
numRows2(s);
function numRows2(sl) {
  const items = [["Notification", "“SEIZURE Bed 3 / GO TO BED 3 NOW: PROTECT FROM INJURY / Heart 120 bpm HIGH | Shaking STRONG”"],
    ["One instruction", "Most urgent first: check breathing > over 5 min > over 2 min > protect from injury"],
    ["Four tiles", "Heart, shaking, muscle, brain: red = act, amber = watch, green = normal"],
    ["Escalation", "At 2 and 5 minutes, reminders until someone taps “On my way”; only a bed name is sent"]];
  items.forEach((it, i) => {
    const y = 2.0 + i * 1.15;
    txt(sl, String(i + 1).padStart(2, "0"), { x: 6.7, y, w: 0.5, h: 0.35, fontSize: 15, bold: true, color: OR, objectName: "Alert number " + (i + 1) });
    txt(sl, it[0], { x: 7.25, y, w: 5.3, h: 0.35, fontSize: 15, bold: true, color: NAVY, objectName: "Alert title " + (i + 1) });
    txt(sl, it[1], { x: 7.25, y: y + 0.38, w: 5.36, h: 0.65, fontSize: 12, objectName: "Alert text " + (i + 1) });
  });
}

// ================================================================ 25 Limitations
pres.addSection({ title: "Conclusion" });
s = content("Conclusion", "SEIZELUT · DISCUSSION", "Limitations", "What the Results Do Not Show Yet", "Strong hardware results, but focal seizures are still mostly missed",
  "Label-free adaptation raised false alarms, so personalisation will need doctor feedback.");
[["Focal seizures", "At the default point the detector finds about one seizure in four; focal seizures are mostly missed, as in the literature [4]."],
 ["Retrospective data", "All results are on recordings of one dataset; no patient wore our hardware."],
 ["Two-stage delay", "The 73.3 % result needs a 96 s delay and about 11 false alarms per hour."],
 ["Alert not on hardware", "The ESP32 alert was tested in emulation; the real-phone test is pending."]].forEach((c, i) => {
  const x = X0 + i * 3.07, w = 2.82;
  s.addShape(pres.shapes.RECTANGLE, { x, y: 2.05, w, h: 3.35, fill: { color: PANEL }, line: { color: PANEL }, objectName: "Limit card " + (i + 1) });
  rule(s, x, 2.05, w, OR2, "Limit rule " + (i + 1));
  txt(s, c[0], { x: x + 0.2, y: 2.35, w: w - 0.4, h: 0.4, fontSize: 16, bold: true, color: NAVY, objectName: "Limit title " + (i + 1) });
  txt(s, c[1], { x: x + 0.2, y: 2.85, w: w - 0.4, h: 2.4, fontSize: 13, objectName: "Limit text " + (i + 1) });
});
panelNote(s, 5.75, "WHAT IT MEANS", "SeizeLUT is a research prototype, not a medical device, until it is tested on people wearing it.", 0.55, "Meaning");

// ================================================================ 26 Conclusion
s = content("Conclusion", "SEIZELUT · CONCLUSION", "Conclusion", "Summary and Future Work", "What we built, and what comes next",
  "Close with the four achievements and the next steps.");
txt(s, "01", { x: X0, y: 2.0, w: 1, h: 0.3, fontSize: 14, bold: true, color: OR, objectName: "Summary number" });
txt(s, "What we showed", { x: X0, y: 2.3, w: 5.7, h: 0.4, fontSize: 18, bold: true, color: NAVY, objectName: "Summary heading" });
rule(s, X0, 2.8, 5.7, NAVY, "Summary rule");
txt(s, [
  "A 50-LUT network: event-F1 0.248 at 0.8 false alarms per day on 29 unseen patients",
  "Whole detector in 1,202 LUTs with no multiplier, running in the KV260 fabric",
  "Self-test catches every decision-changing fault in 10.3 µs; confirmed on the board",
  "All 9 board tests pass; LED, buzzer and doctor alert work in the demo",
].map((t, i, a) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: i < a.length - 1 } })), { x: X0, y: 2.95, w: 5.7, h: 2.8, fontSize: 14, paraSpaceAfter: 8, objectName: "Summary list" });
txt(s, "02", { x: 6.91, y: 2.0, w: 1, h: 0.3, fontSize: 14, bold: true, color: OR, objectName: "Future number" });
txt(s, "Future work", { x: 6.91, y: 2.3, w: 5.7, h: 0.4, fontSize: 18, bold: true, color: OR, objectName: "Future heading" });
rule(s, 6.91, 2.8, 5.7, OR2, "Future rule");
txt(s, [
  "Test the ESP32 alert with a real phone",
  "Learn each patient from doctor feedback, with a new self-test for every update",
  "Wearable prototype on a low-power FPGA; volunteer recordings",
  "Paper submission: IEEE EMBC 2027 (deadline 24 Jan 2027)",
].map((t, i, a) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: i < a.length - 1 } })), { x: 6.91, y: 2.95, w: 5.7, h: 2.8, fontSize: 14, paraSpaceAfter: 8, objectName: "Future list" });
txt(s, "SeizeLUT is a course prototype for research, not a medical device.", { x: X0, y: 6.3, w: W, h: 0.3, fontSize: 12, color: GREY, objectName: "Disclaimer" });

// ================================================================ 27 References
const used = ["gbd2019epilepsy", "elger2018underreporting", "beniczky2021guideline", "swinnen2026seizeit2", "vandecasteele2020bte", "vandecasteele2021ecg", "bhagubai2025seizeit2", "bacellar2024dwn", "petersen2022dlgn", "umuroglu2020logicnets", "zhang2024tcs", "huang2023lightweight", "roy2019chrononet", "dan2024szcore", "khataei2025treelut", "mecik2025thermo", "deaguiar2015wisard", "busia2025fpga", "verma2010micro", "altaf2015jssc", "altaf2016tbcas", "shoaran2018jetcas", "wang2018access", "sopic2018eglass", "busia2024eegformer"];
function shortRef(t) {
  t = t.replace(/\$\$/g, "µ").replace(/\$/g, "").replace(/\.?1em plus 0\.5em minus 0\.4em/g, ". ").replace(/\\'a/g, "á").replace(/'a/g, "á").replace(/ \[Online\]\. Available: \S+/, "").replace(/\s+/g, " ");
  const q = t.indexOf("“");
  let auth = t.slice(0, q).trim().replace(/,$/, "");
  const parts = auth.split(/,\s*|\s+and\s+/).filter(Boolean);
  if (parts.length > 2 && !/et al/.test(auth)) auth = parts[0] + " et al.";
  return (auth + ", " + t.slice(q)).replace(/,\s*,/g, ",");
}
const refs = used.map((k) => [REFS[k][0], shortRef(REFS[k][1])]).sort((a, b) => a[0] - b[0]);
const perSlide = Math.ceil(refs.length / 2);
[refs.slice(0, perSlide), refs.slice(perSlide)].forEach((part, pi) => {
  s = content("Conclusion", "REFERENCES   ·   " + (pi + 1) + " OF 2", "References", "Numbered as in the Report", null, "Only the references cited on these slides; the full list of 79 is in the report.");
  const half = Math.ceil(part.length / 2);
  [part.slice(0, half), part.slice(half)].forEach((col, ci) => {
    s.addText(col.map((r, i) => ({ text: `[${r[0]}]  ${r[1]}`, options: { breakLine: i < col.length - 1 } })), { x: X0 + ci * 6.08, y: 1.7, w: 5.8, h: 4.95, fontSize: 11, color: INK, paraSpaceAfter: 6, margin: 0, valign: "top", isTextBox: true, objectName: "References column " + (ci + 1) });
  });
});

// ================================================================ 28 Thank you
s = pres.addSlide({ masterName: "PLAIN", sectionTitle: "Conclusion" });
txt(s, "Thank you", { x: X0, y: 2.6, w: 9, h: 1.0, fontSize: 44, bold: true, color: NAVY, valign: "middle", objectName: "Thank you" });
txt(s, "Questions are welcome. We can show the live demo on the board.", { x: X0, y: 3.6, w: 9, h: 0.45, fontSize: 18, color: GREY, objectName: "Questions" });
s.addShape(pres.shapes.LINE, { x: X0, y: 5.9, w: W, h: 0, line: { color: LINE, width: 0.75 }, objectName: "Thanks line" });
txt(s, [{ text: "Guide  ", options: { bold: true, color: HX.navy } }, { text: "Prof. V Rama", options: { color: HX.ink, breakLine: true } }, { text: "Project by  ", options: { bold: true, color: HX.navy } }, { text: "Akshara Bonam · Sai Chaithr · Sowjanya", options: { color: HX.ink } }], { x: X0, y: 6.05, w: W, h: 0.6, fontSize: 13, objectName: "Credits" });
s.addNotes("Thank the panel and offer the live demo.");

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
