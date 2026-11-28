// Shows the valve command above the built-in thermostat card and more-info dialog.
// History opens the cover device, so the recorded command is on the graph.
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

function deviceIdFor(hass, entityId) {
  if (!isOurClimate(hass, entityId)) return undefined;
  const entry = hass && hass.entities && hass.entities[entityId];
  return entry && entry.device_id ? entry.device_id : undefined;
}

function deviceHistoryPath(deviceId) {
  const start = new Date();
  start.setDate(start.getDate() - 1);
  start.setHours(0, 0, 0, 0);
  const params = new URLSearchParams();
  params.set("device_id", deviceId);
  params.set("start_date", start.toISOString());
  params.set("back", "1");
  return `/history?${params.toString()}`;
}

function openDeviceHistory(deviceId) {
  const anchor = document.createElement("a");
  anchor.href = deviceHistoryPath(deviceId);
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
}

function patchHistoryButton() {
  customElements.whenDefined("ha-more-info-dialog").then(() => {
    const proto = customElements.get("ha-more-info-dialog").prototype;
    if (proto.__boilerValveHistoryPatched) return;
    proto.__boilerValveHistoryPatched = true;
    const original = proto._goToHistory;
    proto._goToHistory = function goToHistory() {
      try {
        const deviceId = deviceIdFor(this.hass, this._entityId);
        if (deviceId) {
          openDeviceHistory(deviceId);
          return;
        }
      } catch {
        // Fall through to the entity history view.
      }
      if (original) original.call(this);
    };
  });
}

function patchHistoryLink() {
  customElements.whenDefined("ha-more-info-history").then(() => {
    const proto = customElements.get("ha-more-info-history").prototype;
    if (proto.__boilerValveHistoryLinkPatched) return;
    proto.__boilerValveHistoryLinkPatched = true;
    const original = proto.willUpdate;
    proto.willUpdate = function willUpdate(changed) {
      if (original) original.call(this, changed);
      try {
        const deviceId = deviceIdFor(this.hass, this.entityId);
        if (!deviceId || !this._showMoreHref) return;
        const url = new URL(this._showMoreHref, window.location.origin);
        url.searchParams.delete("entity_id");
        url.searchParams.set("device_id", deviceId);
        this._showMoreHref = `${url.pathname}?${url.searchParams.toString()}`;
      } catch {
        // Leave the entity link in place.
      }
    };
  });
}

patchHistoryButton();
patchHistoryLink();

