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
const char *CALL_NUMBER = "+910000000000";     // one-tap call from the alert page (nurse station or emergency team)
const char *PLAN = "Rescue plan: not set. Ask the treating doctor to write it here.";  // the patient's emergency plan

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
bool alarmActive = false, acked = false;       // an alarm event is open; the doctor tapped "On my way"
String ackTime = "";
unsigned long lastPushMs = 0;
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
  String ip = WiFi.localIP().toString();         // buttons in the notification (phone on the same hotspot)
  http.addHeader("Actions", String("http, On my way, http://") + ip + "/ack, method=POST, clear=true; "
                 "view, Open live page, http://" + ip + "/");
  http.setTimeout(8000);
  lastPushCode = http.POST(pushBody + "\n(" + nowText() + ")");
  lastPushWhat = pushTitle;
  lastPushMs = millis();
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
    lastStartMs = now; lastUpdatePushMs = now; alarmActive = true; acked = false; ackTime = "";
    queuePush(lastTitle, lastBody, 5, "rotating_light");
  } else if (ev == "update") {
    // page only; the phone is reminded once a minute until someone acknowledges (see loop)
  } else if (ev == "escalate") {
    alarmActive = true;                         // 2 min and 5 min: always pushed, even after an acknowledgement
    queuePush(lastTitle, lastBody, 5, jsonString(js, "level") == "emergency" ? "sos" : "warning");
  } else if (ev == "end") {
    alarmActive = false;
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
:root{--bg:#0b1020;--card:#141b31;--ink:#e8eeff;--mut:#93a0c0;--red:#ff3049;--amb:#ffb21f;--ok:#2bd67b}
body{margin:0;background:var(--bg);color:var(--ink);font:16px -apple-system,system-ui,sans-serif}
#top{padding:18px 16px 14px;text-align:center;background:#123524}
#top b{display:block;font-size:26px;font-weight:800}#top span{font-size:15px;opacity:.9}
#top.alarm{background:var(--red);animation:fl 1s infinite}#top.long{background:#b5520d;animation:fl 1s infinite}
#top.emergency{background:#8a001a;animation:fl .5s infinite}@keyframes fl{50%{filter:brightness(.6)}}
#sub{color:var(--mut);font-size:13px;text-align:center;margin:8px 16px}
.card{background:var(--card);margin:12px 16px;border-radius:12px;padding:14px 16px}
#danger{display:none;background:#5a0f1c;border:2px solid var(--red);font-weight:700}
.acts{display:flex;gap:10px;margin:12px 16px}.acts>*{flex:1;text-align:center;padding:14px 8px;border-radius:12px;
 font-size:17px;font-weight:700;text-decoration:none;color:#fff;border:0}
#ack{background:#1f6f43}#ack.done{background:#2a3a66;font-weight:500}#call{background:#2a3a66}
.row{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid #222b47}
.row:last-child{border-bottom:0}.k{color:var(--mut);min-width:96px}.v{text-align:right}
h3{margin:0 0 8px;font-size:15px;color:var(--mut);font-weight:600}ol{margin:0;padding-left:20px}li{margin:4px 0}
#snd{display:block;margin:10px auto 0;padding:9px 16px;border-radius:10px;border:0;background:#2a3a66;color:#fff}
#log div{color:var(--mut);font-size:13px;padding:3px 0}.note{color:var(--mut);font-size:12px;text-align:center;margin:10px 16px 24px}
</style></head><body>
<div id="top"><b id="lvl">MONITORING</b><span id="timer"></span></div>
<div id="sub">connecting...</div>
<div class="card" id="danger"></div>
<div class="acts"><button id="ack">On my way</button><a id="call" href="#">Call</a></div>
<button id="snd">Tap once to enable the alarm sound</button>
<div class="card">
<div class="row"><span class="k">Patient</span><span class="v" id="bed">-</span></div>
<div class="row"><span class="k">Alarm</span><span class="v" id="dur">-</span></div>
<div class="row"><span class="k">Alarms</span><span class="v" id="clu">-</span></div>
<div class="row"><span class="k">1 Heart rate</span><span class="v" id="hr">-</span></div>
<div class="row"><span class="k">2 Movement</span><span class="v" id="mov">-</span></div>
<div class="row"><span class="k">3 Muscle (EMG)</span><span class="v" id="emg">-</span></div>
<div class="row"><span class="k">4 Brain (EEG)</span><span class="v" id="eeg">-</span></div>
<div class="row"><span class="k">5 Pattern hint</span><span class="v" id="hint">-</span></div>
<div class="row"><span class="k">Patient button</span><span class="v" id="aware">-</span></div>
<div class="row"><span class="k">Sensors</span><span class="v" id="sens">-</span></div>
</div>
<div class="card"><h3>Patient's emergency plan</h3><div id="plan">-</div></div>
<div class="card"><h3>Seizure first aid (general guidance)</h3><ol>
<li>Note the time; stay with the patient.</li>
<li>Keep them safe: move hard objects away, cushion the head.</li>
<li>Nothing in the mouth; do not hold them down.</li>
<li>When the jerking stops, turn them on their side and check breathing.</li>
<li>Emergency help if it lasts over 5 minutes, another seizure follows, breathing is difficult or there is an injury.</li>
</ol></div>
<div class="card"><h3>Events</h3><div id="log"></div></div>
<div class="note">Measured signs from the SeizeLUT detector for the doctor, not a diagnosis.</div>
<script>
let ac=null,last='',recvAt=0,dur0=0;
const $=id=>document.getElementById(id);
$('snd').onclick=()=>{ac=new (window.AudioContext||window.webkitAudioContext)();beep();$('snd').textContent='Alarm sound on';};
$('ack').onclick=async()=>{try{await fetch('/ack',{method:'POST'});}catch(e){}tick();};
function beep(f){if(!ac)return;const o=ac.createOscillator(),g=ac.createGain();o.frequency.value=f||880;
 o.connect(g);g.connect(ac.destination);g.gain.value=0.2;o.start();o.stop(ac.currentTime+0.25);}
function set(id,v){$(id).textContent=(v===undefined||v===null||v==='')?'-':v;}
function mmss(s){s=Math.max(0,Math.round(s));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');}
async function tick(){
 try{const s=await (await fetch('/state')).json();const m=s.last||{};
  const open=s.alarm_active||(s.alarm_pin&&m.event!=='end');
  const key=(m.event||'')+(m.dur_s||'')+s.last_time;
  if(m.event&&key!==last){last=key;recvAt=Date.now();dur0=m.dur_s||0;
   const d=document.createElement('div');d.textContent=s.last_time+'  '+(m.title||m.event);$('log').insertBefore(d,$('log').firstChild);}
  const dur=open?dur0+(Date.now()-recvAt)/1000:dur0;
  const lvl=!open?'':dur>=300?'emergency':dur>=120?'long':'alarm';
  $('top').className=lvl;
  $('lvl').textContent=lvl==='emergency'?'EMERGENCY: over 5 min':lvl==='long'?'LONG SEIZURE ALARM':open?'SEIZURE ALARM':'MONITORING';
  $('timer').textContent=open?('alarm for '+mmss(dur)+(lvl==='emergency'?' - follow the emergency plan':'')):(m.event==='end'?'last alarm ended after '+mmss(m.dur_s):'');
  const dg=m.danger||[];$('danger').style.display=(open&&dg.length)?'block':'none';$('danger').textContent='Check now: '+dg.join('; ');
  $('ack').textContent=s.acked?('Acknowledged '+s.ack_time):'On my way';$('ack').className=s.acked?'done':'';
  $('call').href='tel:'+s.call;$('call').textContent='Call '+s.call;set('plan',s.plan);
  set('sub',(s.fpga_alive?'FPGA running':'FPGA heartbeat not seen')+' | Wi-Fi '+s.rssi+' dBm | last push: '+s.push+' | '+s.time);
  set('bed',m.bed);set('dur',m.event==='end'?('ended after '+m.dur_s+' s'):(m.dur_s!==undefined?('detector '+(m.conf||'')):(s.alarm_pin?'FPGA alarm signal (no details yet)':'-')));
  set('clu',m.cluster);set('hr',m.hr_text);set('mov',m.mov_text);set('emg',m.emg_text);set('eeg',m.eeg_text);set('hint',m.hint);
  set('aware',m.aware===undefined?'-':(m.aware?'pressed (aware)':'not pressed'));set('sens',m.sensors);
  if(open&&!s.acked){beep(lvl==='emergency'?1320:880);if(navigator.vibrate)navigator.vibrate(300);}
 }catch(e){set('sub','ESP32 not reachable');}
}
setInterval(tick,1000);tick();
</script></body></html>)rawliteral";

void handleRoot() { server.send_P(200, "text/html", PAGE); }

// "On my way": from the page or from the notification's button
void handleAck() {
  if (!acked) {
    acked = true;
    ackTime = nowText();
    Serial.print("{\"event\":\"ack\",\"time\":\"");   // back to the board (dashboard and console)
    Serial.print(ackTime.c_str());
    Serial.print("\"}\n");
  }
  server.send(200, "text/html", "<meta name=viewport content='width=device-width'><h2>Acknowledged</h2>"
              "<p>The alarm page shows that you are on the way.</p><p><a href='/'>Open the live page</a></p>");
}

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
  s += ",\"alarm_active\":"; s += alarmActive ? "true" : "false";
  s += ",\"acked\":"; s += acked ? "true" : "false";
  s += ",\"ack_time\":\"" + ackTime + "\"";
  s += ",\"call\":\"" + String(CALL_NUMBER) + "\"";
  s += ",\"plan\":\"" + String(PLAN) + "\"";
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
  server.on("/ack", handleAck);
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
  if (!pushPending && alarmActive && !acked && lastPushMs && now - lastPushMs >= 60000UL) {
    queuePush(String("REMINDER (not acknowledged): ") + lastTitle, lastBody, 5, "rotating_light");
  }
  if (pushPending) sendPush();
  server.handleClient();
  static unsigned long lastTry = 0;
  if (WiFi.status() != WL_CONNECTED && now - lastTry > 10000UL) { lastTry = now; WiFi.reconnect(); }
}
