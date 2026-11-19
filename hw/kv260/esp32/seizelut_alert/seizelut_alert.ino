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
:root{--bg:#0b1020;--card:#141b31;--ink:#f2f5ff;--mut:#93a0c0;--red:#e0233c;--amb:#e8930c;--grn:#1f9d55;--gry:#3a4462}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:17px -apple-system,system-ui,sans-serif}
#top{padding:16px 16px 12px;text-align:center;background:#16452c}
#top .st{font-size:34px;font-weight:900;letter-spacing:.5px}#top .bt{font-size:20px;font-weight:700;margin-top:2px}
#top.alarm,#top.long{background:var(--red);animation:fl 1s infinite}#top.emergency{background:#7d0016;animation:fl .45s infinite}
#top.ended{background:#3a4462}@keyframes fl{50%{filter:brightness(.62)}}
#act{margin:12px;padding:16px 14px;border-radius:14px;background:#ffd23f;color:#111;font-size:23px;font-weight:900;
 text-align:center;line-height:1.2;display:none}
#danger{margin:0 12px 12px;padding:12px 14px;border-radius:12px;background:#4d0010;border:3px solid var(--red);
 font-size:18px;font-weight:800;display:none}
.acts{display:flex;gap:10px;margin:0 12px 12px}.acts>*{flex:1;text-align:center;padding:16px 6px;border-radius:14px;
 font-size:19px;font-weight:800;text-decoration:none;color:#fff;border:0}
#ack{background:var(--grn)}#ack.done{background:#2a3a66;font-weight:600;font-size:16px}#call{background:#2a3a66}
.tiles{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:0 12px 10px}
.tile{border-radius:14px;padding:12px;background:var(--gry);min-height:86px}
.tile .n{font-size:14px;opacity:.9}.tile .w{font-size:24px;font-weight:900;margin-top:4px}.tile .x{font-size:14px;opacity:.9}
.red{background:var(--red)}.amber{background:var(--amb)}.green{background:var(--grn)}.grey{background:var(--gry)}
#info{margin:0 14px 8px;color:var(--mut);font-size:15px;text-align:center}
details{background:var(--card);margin:8px 12px;border-radius:12px;padding:12px 14px}summary{font-weight:700;font-size:16px}
#detail{white-space:pre-wrap;font-size:15px;line-height:1.45;margin-top:8px}ol{margin:8px 0 0;padding-left:20px}li{margin:4px 0;font-size:15px}
#snd{display:block;margin:4px auto 8px;padding:8px 14px;border-radius:10px;border:0;background:#2a3a66;color:#fff;font-size:14px}
#log div{color:var(--mut);font-size:13px;padding:2px 0}.note{color:var(--mut);font-size:12px;text-align:center;margin:10px 14px 22px}
</style></head><body>
<div id="top"><div class="st" id="st">MONITORING</div><div class="bt" id="bt">&nbsp;</div></div>
<div id="act"></div>
<div id="danger"></div>
<div class="acts"><button id="ack">On my way</button><a id="call" href="#">Call</a></div>
<div class="tiles">
<div class="tile" id="t_heart"><div class="n">Heart rate</div><div class="w">-</div><div class="x"></div></div>
<div class="tile" id="t_shaking"><div class="n">Shaking</div><div class="w">-</div><div class="x"></div></div>
<div class="tile" id="t_muscle"><div class="n">Muscle tension</div><div class="w">-</div><div class="x"></div></div>
<div class="tile" id="t_brain"><div class="n">Brain activity</div><div class="w">-</div><div class="x"></div></div>
</div>
<div id="info"></div>
<button id="snd">Tap once to enable the alarm sound</button>
<details id="dplan"><summary>Emergency plan</summary><div id="plan" style="margin-top:8px">-</div></details>
<details><summary>First aid steps</summary><ol>
<li>Note the time; stay with the patient.</li>
<li>Move hard objects away, cushion the head.</li>
<li>Nothing in the mouth; do not hold them down.</li>
<li>When the jerking stops: turn on the side, check breathing.</li>
<li>Call emergency help if over 5 min, another seizure, breathing difficulty or injury.</li>
</ol></details>
<details><summary>More details</summary><div id="detail">-</div><div id="sub" style="color:#93a0c0;font-size:13px;margin-top:8px"></div></details>
<details><summary>Events</summary><div id="log"></div></details>
<div class="note">Measured signs from the SeizeLUT detector, not a diagnosis.</div>
<script>
let ac=null,last='',recvAt=0,dur0=0;
const $=id=>document.getElementById(id);
$('snd').onclick=()=>{ac=new (window.AudioContext||window.webkitAudioContext)();beep();$('snd').textContent='Alarm sound on';};
$('ack').onclick=async()=>{try{await fetch('/ack',{method:'POST'});}catch(e){}tick();};
function beep(f){if(!ac)return;const o=ac.createOscillator(),g=ac.createGain();o.frequency.value=f||880;
 o.connect(g);g.connect(ac.destination);g.gain.value=0.2;o.start();o.stop(ac.currentTime+0.25);}
function mmss(s){s=Math.max(0,Math.round(s));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');}
function tile(k,v){const e=$('t_'+k);v=v||['-','grey',''];e.className='tile '+v[1];e.querySelector('.w').textContent=v[0];e.querySelector('.x').textContent=v[2]||'';}
async function tick(){
 try{const s=await (await fetch('/state')).json();const m=s.last||{};
  const open=s.alarm_active||(s.alarm_pin&&m.event!=='end');
  const key=(m.event||'')+(m.dur_s||'')+s.last_time;
  if(m.event&&key!==last){last=key;recvAt=Date.now();dur0=m.dur_s||0;
   const d=document.createElement('div');d.textContent=s.last_time+'  '+(m.title||m.event);$('log').insertBefore(d,$('log').firstChild);}
  const dur=open?dur0+(Date.now()-recvAt)/1000:dur0;
  const lvl=open?(dur>=300?'emergency':dur>=120?'long':'alarm'):(m.event==='end'?'ended':'');
  $('top').className=lvl;
  $('st').textContent=lvl==='emergency'?'EMERGENCY':lvl==='long'?'LONG SEIZURE':open?'SEIZURE':lvl==='ended'?'SEIZURE STOPPED':'MONITORING';
  $('bt').innerHTML=(m.bed||'')+(open?' &middot; '+mmss(dur):(lvl==='ended'?' &middot; lasted '+mmss(m.dur_s):'&nbsp;'));
  let act=m.action||'';if(open&&!m.action)act='FPGA ALARM: GO TO THE PATIENT NOW';
  if(open&&lvl==='emergency'&&!(m.danger||[]).length)act='OVER 5 MIN: START EMERGENCY PLAN';
  $('act').style.display=(open||lvl==='ended')&&act?'block':'none';$('act').textContent=act;
  const dg=m.danger||[];$('danger').style.display=(open&&dg.length)?'block':'none';$('danger').textContent='CHECK NOW: '+dg.join('; ');
  $('ack').textContent=s.acked?('On the way since '+s.ack_time):'On my way';$('ack').className=s.acked?'done':'';
  $('call').href='tel:'+s.call;$('call').textContent='Call';
  const T=m.tiles||{};['heart','shaking','muscle','brain'].forEach(k=>tile(k,T[k]));
  const info=[];if((m.alarms_1h||0)>=2)info.push(m.cluster);if(m.aware)info.push('patient pressed the button (aware)');
  $('info').textContent=info.join(' · ');
  $('plan').textContent=s.plan;if(lvl==='emergency')$('dplan').open=true;
  $('detail').textContent=m.detail||'-';
  $('sub').textContent=(s.fpga_alive?'FPGA running':'FPGA heartbeat not seen')+' | Wi-Fi '+s.rssi+' dBm | last push: '+s.push+' | '+s.time;
  if(open&&!s.acked){beep(lvl==='emergency'?1320:880);if(navigator.vibrate)navigator.vibrate(300);}
 }catch(e){$('info').textContent='ESP32 not reachable';}
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
