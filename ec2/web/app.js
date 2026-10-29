// IEE 305 browser MQTT client. Like the Python scripts in students/, this page is
// just another MQTT client: it connects over secure WebSockets on port 443 with the
// class username and password, and the broker's ACL decides what it may do.
"use strict";

const params = new URLSearchParams(location.search);
// Served by the broker host, connect back to it; opened as a local file, use the
// class broker. ?broker=wss://... overrides either.
const BROKER = params.get("broker") ||
  (location.protocol === "https:" ? `wss://${location.host}/mqtt`
                                  : "wss://mqtt.iee305.code-lab.org/mqtt");
const L20_BASE = "iee305/l20/zigbee2mqtt/";
const MAX_ROWS = 200;  // per message table; older rows are dropped

const $ = (id) => document.getElementById(id);
let client = null;       // the page's connection: L-19 log, publishing, L-20 devices
let credentials = null;  // kept in memory only, for the chat connection
let l19Filter = $("filter").value;
const ackCodes = new Map();  // message ID -> MQTT 5 reason code from PUBACK/PUBREC

function show(element, text, kind) {
  element.textContent = text;
  element.classList.remove("ok", "pending", "error");
  if (kind) element.classList.add(kind);
}

// The profanity filter in filter.js masks what other clients send; this refuses
// to send what it would mask.
function refuse(output, ...texts) {
  if (texts.every((text) => clean(text) === text)) return false;
  show(output, "Not sent: remove the blocked words first.", "error");
  return true;
}

function options(extra = {}) {
  // MQTT 5 gives acknowledgments reason codes such as "Not authorized". An empty
  // client ID lets the broker assign a unique one, as in the Python scripts.
  return {
    ...credentials, protocolVersion: 5, clientId: "", clean: true,
    keepalive: 60, connectTimeout: 10000, reconnectPeriod: 5000, ...extra,
  };
}

// ---- Connection ----

$("login").addEventListener("submit", (event) => {
  event.preventDefault();
  if (client) {
    disconnect("Disconnected");
  } else {
    credentials = { username: $("username").value.trim(), password: $("password").value };
    connect();
  }
});

function connect() {
  show($("status"), "Connecting...", "pending");
  $("connect").textContent = "Disconnect";
  let everConnected = false;
  // Subscriptions are made in the connect handler instead of being replayed by
  // MQTT.js, so a reconnect subscribes again just as the Python scripts do.
  client = mqtt.connect(BROKER, options({ resubscribe: false }));
  client.on("connect", (connack) => {
    everConnected = true;
    const id = connack.properties?.assignedClientIdentifier;
    show($("status"), `Connected as ${credentials.username}${id ? `, client ID ${id}` : ""}`, "ok");
    subscribe(l19Filter);
    subscribe(L20_BASE + "#");
  });
  client.on("message", onMessage);
  // The publish callback reports success without the reason code, so record it
  // here to tell "Success" from "No matching subscribers".
  client.on("packetreceive", (packet) => {
    if (packet.cmd === "puback" || packet.cmd === "pubrec") {
      ackCodes.set(packet.messageId, packet.reasonCode ?? 0);
    }
  });
  client.on("error", (err) => {
    if (typeof err.code === "number") {  // a CONNACK reason code: wrong password, etc.
      const reason = err.message.replace(/^Connection refused: /, "");
      disconnect(`Broker refused the login: ${reason}. Check the password.`, "error");
    }
  });
  client.on("reconnect", () => {
    show($("status"), everConnected ? "Connection lost; reconnecting..."
                                    : `Could not reach ${BROKER}; retrying...`, "pending");
  });
}

function disconnect(message, kind) {
  leaveChat();
  client?.end();
  client = null;
  $("connect").textContent = "Connect";
  show($("status"), message, kind);
}

function subscribe(filter) {
  client.subscribe(filter, { qos: 1 }, (err, granted) => {
    // A reason code of 128 or more in the SUBACK means the broker refused it.
    if (err || granted?.some((grant) => grant.qos >= 128)) {
      show($("subscribe-result"), `Subscription to ${filter} refused. Check the topic.`, "error");
    }
  });
}

$("subscribe").addEventListener("submit", (event) => {
  event.preventDefault();
  const filter = $("filter").value.trim();
  if (client?.connected) {
    if (l19Filter !== L20_BASE + "#") client.unsubscribe(l19Filter);
    subscribe(filter);
  }
  l19Filter = filter;
  show($("subscribe-result"), `Showing messages on ${filter}`);
});

// ---- Receiving ----

// MQTT wildcards: + matches exactly one topic level, # matches all remaining levels.
function matches(filter, topic) {
  const f = filter.split("/"), t = topic.split("/");
  for (let i = 0; i < f.length; i++) {
    if (f[i] === "#") return true;
    if (i >= t.length || (f[i] !== "+" && f[i] !== t[i])) return false;
  }
  return f.length === t.length;
}

function onMessage(topic, payload, packet) {
  const text = new TextDecoder().decode(payload);
  if (matches(l19Filter, topic)) addRow($("l19-log"), topic, text, packet);
  if (topic.startsWith(L20_BASE)) {
    addRow($("l20-log"), topic, text, packet);
    updateDevices(topic.slice(L20_BASE.length), text, packet.retain);
  }
}

// The same columns as subscribe.py: receipt time, retain flag, QoS, topic, payload.
function addRow(table, topic, text, packet) {
  const rows = table.tBodies[0];
  const row = rows.insertRow(0);
  const received = new Date().toISOString().slice(11, 19);
  for (const value of [received, packet.retain, packet.qos, clean(topic), clean(text)]) {
    row.insertCell().textContent = value;
  }
  if (rows.rows.length > MAX_ROWS) rows.deleteRow(-1);
}

// ---- Publishing ----

$("publish").addEventListener("submit", (event) => {
  event.preventDefault();
  publish($("pub-topic").value.trim(), $("pub-message").value,
          Number($("pub-qos").value), $("pub-retain").checked, $("publish-result"));
});

// Publish and report the broker's answer, as publish.py does. With QoS 1 or 2 the
// broker acknowledges with a reason code; with QoS 0 there is no acknowledgment.
function publish(topic, message, qos, retain, output) {
  if (!client?.connected) {
    show(output, "Connect first.", "error");
    return;
  }
  if (refuse(output, topic, message)) return;
  client.publish(topic, message, { qos, retain }, (err, packet) => {
    const code = ackCodes.get(packet?.messageId);
    ackCodes.delete(packet?.messageId);
    let answer = "Sent; QoS 0 has no broker acknowledgment";
    if (err) answer = err.message.replace(/^Publish error: /, "");
    else if (qos > 0) answer = code === 16 ? "No matching subscribers" : "Success";
    show(output, `Broker response to ${topic} (qos=${qos}, retain=${retain}): ${answer}`,
         err ? "error" : "ok");
  });
}

// ---- Lecture 20: Zigbee2MQTT devices ----

const devices = new Map();  // friendly name -> card element
const units = new Map();    // friendly name -> { field: unit }
// Fields shown large; the rest are listed below them.
const READINGS = ["temperature", "humidity", "action", "state", "power"];

function parseJson(text) {
  try { return JSON.parse(text); } catch { return null; }
}

// Zigbee2MQTT describes each device's fields, with units, in its "exposes" list.
function unitsOf(exposes = [], found = {}) {
  for (const expose of exposes) {
    if (expose.property && expose.unit) found[expose.property] = expose.unit;
    unitsOf(expose.features, found);
  }
  return found;
}

function updateDevices(subtopic, text, retained) {
  if (subtopic === "bridge/devices") {
    // Zigbee2MQTT keeps its device list as a retained message, so it arrives
    // right after subscribing, before any device reports.
    for (const device of parseJson(text) ?? []) {
      if (device.type !== "Coordinator") card(device.friendly_name, device);
    }
  } else if (!subtopic.startsWith("bridge/") && !/\/(set|get|availability)$/.test(subtopic)) {
    // Anything else is a device's state, published on its friendly name.
    const state = parseJson(text);
    if (state && typeof state === "object") {
      showState(card(subtopic), units.get(subtopic) ?? {}, state, retained);
    }
  }
}

function card(name, device) {
  let element = devices.get(name);
  if (!element) {
    element = $("device-card").content.firstElementChild.cloneNode(true);
    element.querySelector(".name").textContent = name;
    // Commands go to <device>/set. The ACL lets only the instructor publish under
    // iee305/l20/, so a student pressing these buttons sees "Not authorized".
    for (const button of element.querySelectorAll("button[data-state]")) {
      button.addEventListener("click", () => publish(
        `${L20_BASE}${name}/set`, JSON.stringify({ state: button.dataset.state }),
        1, false, element.querySelector(".result")));
    }
    devices.set(name, element);
    $("devices").append(element);
  }
  if (device) {
    const definition = device.definition ?? {};
    element.querySelector(".model").textContent =
      [definition.model, definition.description].filter(Boolean).join(": ");
    units.set(name, unitsOf(definition.exposes));
    // Devices with an on/off switch, such as a wall outlet, get command buttons.
    element.querySelector(".controls").hidden =
      !definition.exposes?.some((expose) => expose.type === "switch");
  }
  return element;
}

function showState(element, fieldUnits, state, retained) {
  for (const [key, value] of Object.entries(state)) {
    // Skip nested objects such as firmware update details, and the empty action
    // that some devices send after a button event.
    if (value === null || typeof value === "object" || (key === "action" && value === "")) continue;
    const text = key === "last_seen" ? new Date(value).toLocaleTimeString()
                                     : `${value}${fieldUnits[key] ? ` ${fieldUnits[key]}` : ""}`;
    const field = setField(element.querySelector(READINGS.includes(key) ? ".readings" : ".details"),
                           key, text);
    if (key === "action" && !retained) flash(field);
  }
  // A retained message is the broker's saved last value, not a fresh observation.
  element.querySelector(".updated").textContent = retained
    ? "Retained value saved by the broker"
    : `Received ${new Date().toLocaleTimeString()}`;
  if (!retained) flash(element);
}

function setField(container, key, text) {
  let field = [...container.children].find((child) => child.dataset.key === key);
  if (!field) {
    field = document.createElement("div");
    field.className = "field";
    field.dataset.key = key;
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = key.replaceAll("_", " ");
    field.append(label, document.createElement("span"));
    container.append(field);
  }
  field.lastChild.textContent = text;
  return field;
}

function flash(element) {
  element.classList.remove("flash");
  void element.offsetWidth;  // restart the CSS animation
  element.classList.add("flash");
}

// ---- Chat, compatible with students/chat.py ----

// Chat opens its own connection, as chat.py does, because a Last Will belongs to a
// connection. Close this tab while in a room and the broker announces
// "(lost connection)"; press Leave and the normal disconnect cancels the will.
let chat = null;

$("chat-join").addEventListener("submit", (event) => {
  event.preventDefault();
  if (chat) {
    leaveChat();
    return;
  }
  if (!client?.connected) {
    show($("chat-result"), "Connect first.", "error");
    return;
  }
  const name = $("chat-name").value.trim();
  const topic = `iee305/l19/class/chat/${$("chat-room").value.trim()}`;
  if (refuse($("chat-result"), name, topic)) return;
  const say = (text) => JSON.stringify({ from: name, text });
  const connection = mqtt.connect(BROKER, options({
    will: { topic, payload: say("(lost connection)"), qos: 1, retain: false },
  }));
  chat = { connection, topic, say };
  connection.on("connect", () => connection.subscribe(topic, { qos: 1 }));
  connection.once("connect", () => {
    connection.publish(topic, say("(joined)"), { qos: 1 });
    show($("chat-result"), `Joined ${topic} as ${name}`, "ok");
    $("chat-button").textContent = "Leave";
    $("chat-send").hidden = false;
  });
  connection.on("message", (_topic, payload) => {
    const text = new TextDecoder().decode(payload);
    const message = parseJson(text);
    const line = document.createElement("li");
    line.textContent = clean(message?.from !== undefined && message?.text !== undefined
      ? `[${message.from}] ${message.text}` : `(not chat JSON) ${text}`);
    $("chat-log").append(line);
    line.scrollIntoView({ block: "nearest" });
  });
});

$("chat-send").addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("chat-text").value.trim();
  if (!chat || !text || refuse($("chat-result"), text)) return;
  chat.connection.publish(chat.topic, chat.say(text), { qos: 1 });
  $("chat-text").value = "";
});

function leaveChat() {
  if (!chat) return;
  const { connection, topic, say } = chat;
  chat = null;
  if (connection.connected) {
    connection.publish(topic, say("(left)"), { qos: 1 }, () => connection.end());
  } else {
    connection.end();
  }
  show($("chat-result"), `Left ${topic}`);
  $("chat-button").textContent = "Join";
  $("chat-send").hidden = true;
}

// ---- Panels: ?lecture=19 or ?lecture=20 starts with only that lecture's panels open ----

const lecture = params.get("lecture");
if (lecture) {
  for (const panel of document.querySelectorAll("details.panel")) {
    panel.open = panel.dataset.lecture === lecture;
  }
}

// ---- Class display: large type and read-only panels, for the projector ----

document.documentElement.classList.toggle("display", params.has("display"));
$("display-toggle").addEventListener("click",
  () => document.documentElement.classList.toggle("display"));
