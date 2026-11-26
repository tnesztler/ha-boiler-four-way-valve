// Shows the valve command above the built-in thermostat card and more-info dialog.
// A target-temperature edit asks for confirmation before it is sent.
const PLATFORM = "boiler_four_way_valve";
const HEROES = ["current_command", "calculated_position"];
const DETAILS = [
  "temperature_difference",
  "outdoor_adjustment",
  "manual_position",
  "max_position",
];
const PERCENT = new Set([
  "current_command",
  "calculated_position",
  "manual_position",
  "max_position",
]);
const TEMPERATURE = new Set(["temperature_difference"]);
const FALLBACK = {
  current_command: "Current command",
  calculated_position: "Calculated position",
  temperature_difference: "Temperature difference",
  outdoor_adjustment: "Outdoor adjustment",
  manual_position: "Manual position",
  max_position: "Maximum position",
};
const LABEL_KEY =
  "component.boiler_four_way_valve.entity.climate.boiler_four_way_valve.state_attributes.";

const STYLE = `
  :host {
    display: block;
    width: 100%;
    box-sizing: border-box;
    flex: none;
    align-self: stretch;
    color: var(--primary-text-color);
    border-bottom: 1px solid var(--divider-color);
    padding: 4px 12px 8px;
    margin: 0 0 8px;
  }
  .heroes {
    display: grid;
    grid-template-columns: 1fr 1fr;
    text-align: center;
    margin-bottom: 8px;
  }
  .label {
    margin: 0 0 2px;
    opacity: 0.8;
    font-size: var(--ha-font-size-s, 12px);
    line-height: var(--ha-line-height-condensed, 1.2);
  }
  .value {
    margin: 0;
    font-size: var(--ha-font-size-xl, 20px);
    font-weight: var(--ha-font-weight-medium, 500);
    line-height: var(--ha-line-height-condensed, 1.2);
    font-variant-numeric: tabular-nums;
    direction: ltr;
  }
  .details {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2px 12px;
  }
  .detail {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    min-width: 0;
    font-size: var(--ha-font-size-s, 12px);
    line-height: var(--ha-line-height-normal, 1.4);
  }
  .k {
    color: var(--secondary-text-color);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .v {
    flex: none;
    font-variant-numeric: tabular-nums;
    direction: ltr;
  }
`;

class BoilerFourWayValvePanel extends HTMLElement {
  constructor() {
    super();
    this._hass = undefined;
    this._state = undefined;
    const root = this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = STYLE;
    this._body = document.createElement("div");
    root.append(style, this._body);
  }

  update(hass, stateObj) {
    this._hass = hass;
    this._state = stateObj;
    this._render();
  }

  _render() {
    const state = this._state;
    this._body.replaceChildren();
    if (!state) {
      return;
    }
    const heroes = document.createElement("div");
    heroes.className = "heroes";
    HEROES.forEach((key) => {
      const cell = document.createElement("div");
      cell.append(
        labeled("p", "label", attributeLabel(this._hass, key)),
        labeled("p", "value", formatValue(this._hass, state, key)),
      );
      heroes.append(cell);
    });
    const details = document.createElement("div");
    details.className = "details";
    DETAILS.forEach((key) => {
      const row = document.createElement("div");
      row.className = "detail";
      row.append(
        labeled("span", "k", attributeLabel(this._hass, key)),
        labeled("span", "v", formatValue(this._hass, state, key)),
      );
      details.append(row);
    });
    this._body.append(heroes, details);
  }
}

if (!customElements.get("boiler-four-way-valve-panel")) {
  customElements.define("boiler-four-way-valve-panel", BoilerFourWayValvePanel);
}

function labeled(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

function attributeLabel(hass, key) {
  const full = `${LABEL_KEY}${key}.name`;
  const translated = hass && hass.localize ? hass.localize(full) : "";
  if (translated && translated !== full) {
    return translated;
  }
  return FALLBACK[key];
}

function formatValue(hass, state, key) {
  const value = asNumber(state.attributes && state.attributes[key]);
  if (value === null) {
    return "—";
  }
  if (PERCENT.has(key)) {
    return `${formatNumber(value, 1)}%`;
  }
  if (TEMPERATURE.has(key)) {
    const unit =
      (hass && hass.config && hass.config.unit_system && hass.config.unit_system.temperature) ||
      "";
    const text = formatNumber(value, 1);
    return unit ? `${text} ${unit}` : text;
  }
  const signed = value > 0 ? `+${formatNumber(value, 1)}` : formatNumber(value, 1);
  return `${signed}%`;
}

function formatNumber(value, digits) {
  const factor = 10 ** digits;
  const rounded = Math.round(value * factor) / factor;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(digits);
}

function asNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function homeAssistant() {
  const root = document.querySelector("home-assistant");
  return root ? root.hass : undefined;
}

function isValveClimate(hass, entityId) {
  if (!hass || !entityId || !hass.entities) {
    return false;
  }
  const entry = hass.entities[entityId];
  return Boolean(entry && entry.platform === PLATFORM);
}

function ensurePanel(host) {
  if (!host.__boilerFourWayValvePanel) {
    host.__boilerFourWayValvePanel = document.createElement(
      "boiler-four-way-valve-panel",
    );
  }
  return host.__boilerFourWayValvePanel;
}

function detachPanel(host) {
  const panel = host.__boilerFourWayValvePanel;
  if (panel && panel.parentElement) {
    panel.remove();
  }
}

function syncMoreInfo(element) {
  const state = element.stateObj;
  const hass = homeAssistant();
  if (!element.shadowRoot || !state || !isValveClimate(hass, state.entity_id)) {
    detachPanel(element);
    return;
  }
  const panel = ensurePanel(element);
  if (panel.parentElement !== element.shadowRoot) {
    element.shadowRoot.prepend(panel);
  }
  panel.update(hass, state);
}

function syncThermostatCard(element) {
  const card = element.shadowRoot && element.shadowRoot.querySelector("ha-card");
  const hass = element.hass || homeAssistant();
  const state = thermostatState(element, hass);
  if (!card || !state || !isValveClimate(hass, state.entity_id)) {
    detachPanel(element);
    return;
  }
  const panel = ensurePanel(element);
  const title = card.querySelector(".title");
  const anchor = title || null;
  if (anchor && panel.previousElementSibling !== anchor) {
    anchor.after(panel);
  } else if (!anchor && card.firstElementChild !== panel) {
    card.prepend(panel);
  }
  panel.update(hass, state);
}

function thermostatState(element, hass) {
  const control =
    element.shadowRoot &&
    element.shadowRoot.querySelector("ha-state-control-climate-temperature");
  if (control && control.stateObj && control.stateObj.entity_id) {
    return control.stateObj;
  }
  const entityId = element._config && element._config.entity;
  if (entityId && hass && hass.states) {
    return hass.states[entityId];
  }
  return undefined;
}

function patch(tag, sync) {
  customElements.whenDefined(tag).then(() => {
    const proto = customElements.get(tag).prototype;
    if (proto.__boilerFourWayValvePatched) {
      return;
    }
    proto.__boilerFourWayValvePatched = true;
    const original = proto.updated;
    proto.updated = function updated(changed) {
      if (original) {
        original.call(this, changed);
      }
      try {
        sync(this);
      } catch {
        // A panel failure must leave the thermostat control usable.
      }
    };
  });
}

patch("more-info-climate", syncMoreInfo);
patch("hui-thermostat-card", syncThermostatCard);

const CONFIRM_STYLE = `
  .boiler-valve-confirm {
    position: fixed;
    inset: 0;
    z-index: 100000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    box-sizing: border-box;
    background: rgba(0, 0, 0, 0.45);
  }
  .boiler-valve-confirm .box {
    width: min(100%, 360px);
    box-sizing: border-box;
    margin: 0;
    padding: 20px 20px 16px;
    border-radius: var(--ha-card-border-radius, 12px);
    background: var(--card-background-color, var(--ha-card-background, var(--primary-background-color)));
    color: var(--primary-text-color);
    box-shadow: var(--ha-card-box-shadow, 0 8px 24px rgba(0, 0, 0, 0.24));
  }
  .boiler-valve-confirm h2 {
    margin: 0 0 8px;
    font-size: var(--ha-font-size-l, 18px);
    font-weight: var(--ha-font-weight-medium, 500);
    line-height: var(--ha-line-height-condensed, 1.2);
  }
  .boiler-valve-confirm p {
    margin: 0 0 20px;
    font-size: var(--ha-font-size-m, 14px);
    line-height: var(--ha-line-height-normal, 1.4);
  }
  .boiler-valve-confirm .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
  .boiler-valve-confirm button {
    margin: 0;
    padding: 8px 16px;
    border-radius: var(--ha-border-radius-md, 8px);
    font: inherit;
    font-size: var(--ha-font-size-m, 14px);
    cursor: pointer;
  }
  .boiler-valve-confirm .cancel {
    background: transparent;
    color: var(--primary-text-color);
    border: 1px solid var(--divider-color);
  }
  .boiler-valve-confirm .change {
    background: var(--primary-color);
    color: var(--text-primary-color, #fff);
    border: 1px solid transparent;
  }
`;

let confirmQueue = Promise.resolve();

function listedEntities(data, target) {
  const raw = (data && data.entity_id) || (target && target.entity_id);
  if (!raw) return [];
  return Array.isArray(raw) ? raw : [raw];
}

function isOurClimate(hass, entityId) {
  if (isValveClimate(hass, entityId)) return true;
  const state = hass && hass.states && hass.states[entityId];
  const attributes = state && state.attributes;
  return Boolean(
    attributes &&
      "current_command" in attributes &&
      "calculated_position" in attributes &&
      "temperature_difference" in attributes,
  );
}

function setpointChange(hass, domain, service, data, target) {
  if (domain !== "climate" || service !== "set_temperature" || !data) return null;
  const next = Number(data.temperature);
  if (!Number.isFinite(next)) return null;
  const entityId = listedEntities(data, target).find((id) => isOurClimate(hass, id));
  if (!entityId) return null;
  const state = hass.states && hass.states[entityId];
  const current = state && state.attributes ? Number(state.attributes.temperature) : NaN;
  if (Number.isFinite(current) && Math.abs(current - next) < 0.05) return null;
  return { entityId, current, next };
}

function temperatureUnit(hass) {
  const unit =
    hass && hass.config && hass.config.unit_system && hass.config.unit_system.temperature;
  return unit || "°C";
}

function formatTemperature(value, unit) {
  if (!Number.isFinite(value)) return "—";
  return `${value.toFixed(1)} ${unit}`;
}

function localized(hass, key, fallback) {
  if (!hass || !hass.localize) return fallback;
  const value = hass.localize(key);
  if (!value || value === key) return fallback;
  return value;
}

function ensureConfirmStyle() {
  if (document.getElementById("boiler-valve-confirm-style")) return;
  const style = document.createElement("style");
  style.id = "boiler-valve-confirm-style";
  style.textContent = CONFIRM_STYLE;
  document.head.append(style);
}

function askConfirm(hass, entityId, current, next) {
  ensureConfirmStyle();
  const state = hass.states && hass.states[entityId];
  const name = state && state.attributes && state.attributes.friendly_name;
  const unit = temperatureUnit(hass);
  const from = formatTemperature(current, unit);
  const to = formatTemperature(next, unit);
  const detail = name
    ? `Change the ${name} target from ${from} to ${to}?`
    : `Change the target from ${from} to ${to}?`;

  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "boiler-valve-confirm";
    const box = document.createElement("div");
    box.className = "box";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-labelledby", "boiler-valve-confirm-title");
    const title = document.createElement("h2");
    title.id = "boiler-valve-confirm-title";
    title.textContent = "Change target temperature";
    const text = document.createElement("p");
    text.textContent = detail;
    const actions = document.createElement("div");
    actions.className = "actions";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "cancel";
    cancel.textContent = localized(hass, "ui.common.cancel", "Cancel");
    const change = document.createElement("button");
    change.type = "button";
    change.className = "change";
    change.textContent = "Change";
    actions.append(cancel, change);
    box.append(title, text, actions);
    overlay.append(box);

    const previous = document.activeElement;
    function finish(ok) {
      document.removeEventListener("keydown", onKey, true);
      overlay.remove();
      if (previous && previous.focus) previous.focus();
      resolve(ok);
    }
    function onKey(event) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      finish(false);
    }

    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) finish(false);
    });
    cancel.addEventListener("click", () => finish(false));
    change.addEventListener("click", () => finish(true));
    document.addEventListener("keydown", onKey, true);
    document.body.append(overlay);
    cancel.focus();
  });
}

function enqueueConfirm(hass, entityId, current, next) {
  const job = confirmQueue.then(
    () => askConfirm(hass, entityId, current, next),
    () => askConfirm(hass, entityId, current, next),
  );
  confirmQueue = job.then(
    () => undefined,
    () => undefined,
  );
  return job;
}

function adoptGuard(guarded) {
  const root = document.querySelector("home-assistant");
  if (!root) return;
  const visitChildren = (node) => {
    const kids = node.children;
    if (!kids) return;
    for (let index = 0; index < kids.length; index += 1) visit(kids[index]);
  };
  const visit = (node) => {
    if (!node) return;
    if (node.nodeType === 1 && node._api && typeof node._api.callService === "function") {
      node._api.callService = guarded;
    }
    if (node.shadowRoot) visitChildren(node.shadowRoot);
    visitChildren(node);
  };
  visit(root);
}

function installGuard(hass) {
  if (!hass || typeof hass.callService !== "function") return;
  if (hass.callService.__boilerValveGuard) return;
  const original = hass.callService.bind(hass);
  function guarded(domain, service, data, target) {
    const extra = [];
    for (let index = 4; index < arguments.length; index += 1) {
      extra.push(arguments[index]);
    }
    const change = setpointChange(hass, domain, service, data, target);
    const send = () => original(domain, service, data, target, ...extra);
    if (!change) return send();
    return enqueueConfirm(hass, change.entityId, change.current, change.next).then((ok) => {
      if (!ok) {
        const error = new Error("Target change cancelled");
        error.code = "boiler_four_way_valve_cancelled";
        return Promise.reject(error);
      }
      return send();
    });
  }
  guarded.__boilerValveGuard = true;
  hass.callService = guarded;
  adoptGuard(guarded);
}

function watchServiceCalls() {
  customElements.whenDefined("home-assistant").then(() => {
    const proto = customElements.get("home-assistant").prototype;
    if (!proto.__boilerValveHassPatched) {
      proto.__boilerValveHassPatched = true;
      const original = proto.updated;
      proto.updated = function updated(changed) {
        try {
          installGuard(this.hass);
        } catch {
          // A confirm-dialog failure must leave the thermostat control usable.
        }
        if (original) original.call(this, changed);
      };
    }
    const root = document.querySelector("home-assistant");
    if (root && root.hass) installGuard(root.hass);
  });
}

watchServiceCalls();
