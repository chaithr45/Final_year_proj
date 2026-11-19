// SeizeLUT doctor alert on an ESP32 (Arduino). The KV260 detects seizures in its FPGA; this ESP32 tells the doctor.
//
//   KV260 USB port --USB cable--> ESP32 USB: power + one JSON message per line (demo/doctor_alert.py on the board):
//                                  alarm start, updates every 15 s, end, patient button, with five measured details
//   KV260 PMOD B1 (alarm, 3.3 V) --wire--> GPIO 27   backup: the FPGA's own alarm output (needs no board software)
//   KV260 PMOD B3 (heartbeat)    --wire--> GPIO 26   optional: toggles once per window, shows the FPGA is running
//   KV260 PMOD GND               --wire--> GND       shared ground (do NOT connect PMOD 3.3 V to the ESP32)
//
// Out: a push notification on the doctor's phone through ntfy (free app for iPhone and Android, works anywhere with
// internet), and a live web page at http://<ESP32 address>/ on the same Wi-Fi (the phone's hotspot).
// Measured signs for the doctor, not a diagnosis.
//
// Fill in the four settings below, then Tools > Board > "ESP32 Dev Module", choose the port, Upload.
#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <time.h>

// ------------------------------------------------------------------------------------------------ settings
const char *WIFI_SSID = "SaiPhone";            // your iPhone's hotspot name (Settings > General > About > Name)
const char *WIFI_PASS = "change-me";           // Settings > Personal Hotspot > Wi-Fi Password
const char *NTFY_TOPIC = "seizelut-change-me-7c3f9a";  // a long random name; subscribe to it in the ntfy app
const char *BED = "Bed 1";                     // shown when the board sends nothing (backup alarm)
const long TZ_OFFSET_S = 19800;                // India: UTC+5:30

const int ALARM_PIN = 27;                      // PMOD B1
const int HB_PIN = 26;                         // PMOD B3 (optional)
const int LED_PIN = 2;                         // the DevKit's blue LED: on while the alarm is on

// ------------------------------------------------------------------------------------------------ state
WebServer server(80);
String lineBuf;
String lastJson = "null";                      // the last message from the board, served to the web page as is
String lastEvent = "", lastTitle = "", lastBody = "", lastTime = "";
unsigned long lastMsgMs = 0, lastStartMs = 0, lastUpdatePushMs = 0, pinHighSinceMs = 0, lastHbMs = 0;
bool pinAlarm = false, backupSent = false, hbLevel = false;
int lastPushCode = 0;
String lastPushWhat = "none";

// a push waiting to be sent from loop()
bool pushPending = false;
String pushTitle, pushBody, pushTags;
int pushPriority = 3;

String nowText() {
  struct tm t;
  if (!getLocalTime(&t, 10)) return String("time n/a");
  char buf[24];
  strftime(buf, sizeof(buf), "%H:%M:%S", &t);
  return String(buf);
}

// value of "key":"..." in a one-line JSON object (the board writes plain ASCII; \n, \" and \\ are unescaped)
String jsonString(const String &js, const char *key) {
  String pat = String("\"") + key + "\":\"";
  int i = js.indexOf(pat);
  if (i < 0) return String("");
  i += pat.length();
  String out;
  while (i < (int)js.length()) {
    char c = js[i++];
    if (c == '"') break;
    if (c == '\\' && i < (int)js.length()) {
      char e = js[i++];
      if (e == 'n') out += '\n';
      else if (e == 'u') { i += 4; out += '?'; }
      else out += e;
    } else {
      out += c;
    }
  }
  return out;
}

void queuePush(const String &title, const String &body, int priority, const String &tags) {
  pushTitle = title; pushBody = body; pushPriority = priority; pushTags = tags; pushPending = true;
}

void sendPush() {
  pushPending = false;
  if (WiFi.status() != WL_CONNECTED) { lastPushCode = -1; lastPushWhat = pushTitle + " (no Wi-Fi)"; return; }
  WiFiClientSecure client;
  client.setInsecure();                        // demo: no certificate check (see esp32/README.md)
  HTTPClient http;
  String url = String("https://ntfy.sh/") + NTFY_TOPIC;
  if (!http.begin(client, url)) { lastPushCode = -2; return; }
  http.addHeader("Title", pushTitle);
  http.addHeader("Priority", String(pushPriority));
  http.addHeader("Tags", pushTags);
  http.setTimeout(8000);
  lastPushCode = http.POST(pushBody + "\n(" + nowText() + ")");
  lastPushWhat = pushTitle;
  http.end();
  Serial.printf("# push %d: %s\n", lastPushCode, pushTitle.c_str());
}

// one message from the board
void handleLine(const String &js) {
  String ev = jsonString(js, "event");
  if (ev.length() == 0) return;
  lastJson = js; lastEvent = ev; lastTitle = jsonString(js, "title"); lastBody = jsonString(js, "body");
  lastTime = nowText(); lastMsgMs = millis();
  unsigned long now = millis();
  if (ev == "start") {
    lastStartMs = now; lastUpdatePushMs = now;
    queuePush(lastTitle, lastBody, 5, "rotating_light");
  } else if (ev == "update") {
    if (now - lastUpdatePushMs >= 60000UL) {   // the page updates every 15 s; the phone at most once a minute
      lastUpdatePushMs = now;
      queuePush(lastTitle, lastBody, 4, "warning");
    }
  } else if (ev == "end") {
    queuePush(lastTitle, lastBody, 3, "white_check_mark");
  } else if (ev == "button") {
    queuePush(lastTitle, lastBody, 4, "raising_hand");
  } else if (ev == "hello") {
    queuePush(lastTitle, lastBody, 2, "satellite");
  }
}

// ------------------------------------------------------------------------------------------------ web page
const char PAGE[] PROGMEM = R"rawliteral(<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SeizeLUT alert</title>
<style>
:root{--bg:#0b1020;--card:#141b31;--ink:#e8eeff;--mut:#93a0c0;--red:#ff3049;--ok:#2bd67b}
body{margin:0;background:var(--bg);color:var(--ink);font:16px -apple-system,system-ui,sans-serif}
#top{padding:22px 16px;text-align:center;font-weight:800;font-size:26px;background:#123524}
#top.alarm{background:var(--red);animation:fl 1s infinite}@keyframes fl{50%{background:#7a0f1d}}
#sub{color:var(--mut);font-size:14px;text-align:center;margin:8px 16px}
.card{background:var(--card);margin:12px 16px;border-radius:12px;padding:14px 16px}
.row{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid #222b47}
.row:last-child{border-bottom:0}.k{color:var(--mut);min-width:96px}.v{text-align:right}
button{display:block;margin:12px auto;padding:10px 18px;border-radius:10px;border:0;background:#2a3a66;color:#fff;font-size:15px}
#log div{color:var(--mut);font-size:13px;padding:3px 0}.note{color:var(--mut);font-size:12px;text-align:center;margin:10px 16px 24px}
</style></head><body>
<div id="top">MONITORING</div><div id="sub">connecting...</div>
<button id="snd">Tap once to enable the alarm sound</button>
<div class="card" id="det">
<div class="row"><span class="k">Patient</span><span class="v" id="bed">-</span></div>
<div class="row"><span class="k">Alarm</span><span class="v" id="dur">-</span></div>
<div class="row"><span class="k">1 Heart rate</span><span class="v" id="hr">-</span></div>
<div class="row"><span class="k">2 Movement</span><span class="v" id="mov">-</span></div>
<div class="row"><span class="k">3 Muscle (EMG)</span><span class="v" id="emg">-</span></div>
<div class="row"><span class="k">4 Brain (EEG)</span><span class="v" id="eeg">-</span></div>
<div class="row"><span class="k">5 Pattern hint</span><span class="v" id="hint">-</span></div>
<div class="row"><span class="k">Patient button</span><span class="v" id="aware">-</span></div>
<div class="row"><span class="k">Sensors</span><span class="v" id="sens">-</span></div>
</div>
<div class="card"><div class="k" style="margin-bottom:6px">Events</div><div id="log"></div></div>
<div class="note">Measured signs from the SeizeLUT detector for the doctor, not a diagnosis.</div>
<script>
let ac=null,last='',alarmOn=false;
document.getElementById('snd').onclick=()=>{ac=new (window.AudioContext||window.webkitAudioContext)();beep();
 document.getElementById('snd').textContent='Alarm sound on';};
function beep(){if(!ac)return;const o=ac.createOscillator(),g=ac.createGain();o.frequency.value=880;
 o.connect(g);g.connect(ac.destination);g.gain.value=0.2;o.start();o.stop(ac.currentTime+0.25);}
function set(id,v){document.getElementById(id).textContent=(v===undefined||v===null||v==='')?'-':v;}
async function tick(){
 try{const s=await (await fetch('/state')).json();const m=s.last||{};
  const on=s.alarm_pin||(m.event==='start'||m.event==='update');
  const top=document.getElementById('top');
  top.textContent=on?'SEIZURE ALARM':'MONITORING';top.className=on?'alarm':'';
  set('sub',(s.fpga_alive?'FPGA running':'FPGA heartbeat not seen')+' | Wi-Fi '+s.rssi+' dBm | last push: '+s.push+' | '+s.time);
  set('bed',m.bed);set('dur',m.event==='end'?('ended after '+m.dur_s+' s'):(m.dur_s!==undefined?(m.dur_s+' s, detector '+(m.conf||'')):(s.alarm_pin?'FPGA alarm signal (no details yet)':'-')));
  set('hr',m.hr_text);set('mov',m.mov_text);set('emg',m.emg_text);set('eeg',m.eeg_text);set('hint',m.hint);
  set('aware',m.aware===undefined?'-':(m.aware?'pressed (aware)':'not pressed'));set('sens',m.sensors);
  const key=(m.event||'')+(m.dur_s||'')+s.last_time;
  if(m.event&&key!==last){last=key;const d=document.createElement('div');d.textContent=s.last_time+'  '+(m.title||m.event);
   const L=document.getElementById('log');L.insertBefore(d,L.firstChild);}
  if(on){beep();if(navigator.vibrate)navigator.vibrate(300);}
 }catch(e){set('sub','ESP32 not reachable');}
}
setInterval(tick,1000);tick();
</script></body></html>)rawliteral";

void handleRoot() { server.send_P(200, "text/html", PAGE); }

void handleState() {
  String s = "{\"alarm_pin\":";
  s += pinAlarm ? "true" : "false";
  s += ",\"fpga_alive\":";
  s += (lastHbMs && millis() - lastHbMs < 5000UL) ? "true" : "false";
  s += ",\"rssi\":" + String(WiFi.RSSI());
  String push = "none yet";
  if (lastPushCode == 200) push = "sent";
  else if (lastPushCode != 0) push = String("error ") + String(lastPushCode);
  s += ",\"push\":\"" + push + "\"";
  s += ",\"time\":\"" + nowText() + "\"";
  s += ",\"last_time\":\"" + lastTime + "\"";
  s += ",\"last\":" + lastJson + "}";
  server.send(200, "application/json", s);
}

// ------------------------------------------------------------------------------------------------ setup / loop
void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(250);
}

void setup() {
  Serial.setRxBufferSize(4096);                // before begin(): room for one long message
  Serial.begin(115200);
  pinMode(ALARM_PIN, INPUT_PULLDOWN);
  pinMode(HB_PIN, INPUT_PULLDOWN);
  pinMode(LED_PIN, OUTPUT);
  connectWifi();
  configTime(TZ_OFFSET_S, 0, "pool.ntp.org", "time.google.com");
  server.on("/", handleRoot);
  server.on("/state", handleState);
  server.begin();
  Serial.print("# SeizeLUT alert ready, page: http://");
  Serial.println(WiFi.localIP());
}

void loop() {
  // messages from the board
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') { handleLine(lineBuf); lineBuf = ""; }
    else if (c != '\r' && lineBuf.length() < 4000) lineBuf += c;
  }
  // the FPGA's alarm wire (backup) and heartbeat
  unsigned long now = millis();
  bool p = digitalRead(ALARM_PIN);
  if (p && !pinAlarm) { pinHighSinceMs = now; backupSent = false; }
  pinAlarm = p;
  digitalWrite(LED_PIN, p ? HIGH : LOW);
  if (p && !backupSent && now - pinHighSinceMs > 4000UL && !(lastStartMs && now - lastStartMs < 30000UL)) {
    backupSent = true;                         // alarm on for 4 s and no details from the board: alert anyway
    queuePush(String("SEIZURE ALARM (FPGA signal) - ") + BED,
              "The FPGA's alarm output is on, but no details came from the board. Check the patient.", 5,
              "rotating_light");
  }
  bool hb = digitalRead(HB_PIN);
  if (hb != hbLevel) { hbLevel = hb; lastHbMs = now; }
  if (pushPending) sendPush();
  server.handleClient();
  static unsigned long lastTry = 0;
  if (WiFi.status() != WL_CONNECTED && now - lastTry > 10000UL) { lastTry = now; WiFi.reconnect(); }
}
