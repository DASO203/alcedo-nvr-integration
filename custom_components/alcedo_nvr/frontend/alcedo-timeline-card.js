/*
 * Alcedo NVR – timeline & timelapse card for Home Assistant dashboards.
 *
 *   type: custom:alcedo-timeline-card
 *   title: Kameras
 *   hours: 24                 # default period
 *   periods: [24, 72, 168]    # period buttons (hours)
 *   cameras: [einfahrt, garten]   # optional filter (camera ids or names)
 *   show_rejected: true       # show events the AI rejected
 *   timelapse_mode: clips     # clips | snapshots
 *   timelapse_speed: 4        # 1..16
 *   only_confirmed: true      # timelapse with confirmed alarms only
 *
 * Shipped and registered automatically by the Alcedo NVR integration.
 */

const TEXT = {
  de: {
    title: "Alcedo Zeitstrahl", timelapse: "Zeitraffer", building: "Zeitraffer wird erstellt",
    empty: "Keine Ereignisse in diesem Zeitraum.", noRec: "Zu dieser Zeit gibt es keine Aufnahme.",
    rec: "Aufnahme ab", alarm: "Alarm", rejected: "verworfen", pending: "in Prüfung",
    error: "Alcedo NVR nicht erreichbar", noCams: "Keine Kameras.", days: "T", hours: "h",
    noClip: "Kein Clip – Snapshot:", events: "Ereignisse", alarms: "Alarme", cloud: "aus pCloud",
  },
  en: {
    title: "Alcedo timeline", timelapse: "Timelapse", building: "Building timelapse",
    empty: "No events in this period.", noRec: "No recording at this time.",
    rec: "Recording from", alarm: "alarm", rejected: "rejected", pending: "pending",
    error: "Alcedo NVR not reachable", noCams: "No cameras.", days: "d", hours: "h",
    noClip: "No clip – snapshot:", events: "events", alarms: "alarms", cloud: "from pCloud",
  },
};

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

class AlcedoTimelineCard extends HTMLElement {
  static getStubConfig() {
    return { title: "Alcedo NVR", hours: 24 };
  }

  setConfig(config) {
    this._cfg = {
      hours: 24, periods: [24, 72, 168], entry_id: "_", show_rejected: true,
      timelapse_mode: "clips", timelapse_speed: 4, only_confirmed: true, ...config,
    };
    this._hours = Number(this._cfg.hours) || 24;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._renderShell();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._start();
  }

  connectedCallback() {
    if (this._hass && !this._timer) this._start();
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    clearTimeout(this._poll);
    this._timer = undefined;
  }

  getCardSize() {
    return 3 + ((this._data && this._data.cameras.length) || 2);
  }

  _start() {
    this._renderShell(); // labels in the user's language
    this._load();
    clearInterval(this._timer);
    this._timer = setInterval(() => this._load(), 60000);
  }

  _t(key) {
    const lang = (this._hass && this._hass.language || "en").startsWith("de") ? "de" : "en";
    return TEXT[lang][key];
  }

  _api(method, path, body) {
    return this._hass.callApi(method, `alcedo_nvr/${this._cfg.entry_id}/${path}`, body);
  }

  async _signed(path) {
    const res = await this._hass.callWS({
      type: "auth/sign_path", path: `/api/alcedo_nvr/${this._cfg.entry_id}/file/${path}`, expires: 3600,
    });
    return res.path;
  }

  _renderShell() {
    const c = this._cfg;
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 12px 16px 16px; }
        .head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
        .title { font-size: 1.15em; font-weight: 500; flex: 1; min-width: 120px; }
        button { border: 1px solid var(--divider-color); background: var(--card-background-color);
          color: var(--primary-text-color); border-radius: 16px; padding: 4px 12px; cursor: pointer; font: inherit; }
        button.on { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
        button.tl { border-color: var(--primary-color); color: var(--primary-color); }
        .scale { position: relative; height: 16px; margin-left: var(--alc-name, 110px); font-size: 11px; color: var(--secondary-text-color); }
        .scale span { position: absolute; transform: translateX(-50%); white-space: nowrap; }
        .row { display: grid; grid-template-columns: var(--alc-name, 110px) 1fr; gap: 8px; align-items: center; min-height: 32px; }
        .name { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .name small { display: block; font-weight: 400; color: var(--secondary-text-color); font-size: 11px; }
        .track { position: relative; height: 24px; border-radius: 6px; cursor: crosshair;
          background: var(--secondary-background-color, rgba(127,127,127,.12)); }
        .rec { position: absolute; top: 9px; height: 6px; border-radius: 3px; background: var(--primary-color); opacity: .35; }
        .ev { position: absolute; top: 2px; width: 6px; height: 20px; border-radius: 3px; transform: translateX(-3px); cursor: pointer; }
        .ev.c { background: var(--error-color, #db4437); }
        .ev.r { background: var(--disabled-text-color, #9e9e9e); }
        .ev.p { background: var(--warning-color, #ffa600); }
        .ev.a { box-shadow: 0 0 0 2px var(--card-background-color, #fff) inset; opacity: .85; }
        .now { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--primary-color); }
        .status { color: var(--secondary-text-color); font-size: 13px; margin-top: 8px; min-height: 18px; }
        .status a { color: var(--primary-color); }
        progress { width: 100%; height: 6px; margin-top: 4px; display: none; }
        video, img.snap { width: 100%; border-radius: 8px; margin-top: 8px; background: #000; display: none; }
        @media (max-width: 500px) { :host { --alc-name: 72px; } }
      </style>
      <ha-card>
        <div class="head">
          <div class="title">${esc(c.title || this._t("title"))}</div>
          ${c.periods.map((h) => `<button class="period" data-h="${h}">${h % 24 === 0 && h > 24 ? `${h / 24} ${this._t("days")}` : `${h} ${this._t("hours")}`}</button>`).join("")}
          <button class="tl" id="timelapse">▶ ${this._t("timelapse")}</button>
        </div>
        <div id="timeline"></div>
        <div class="status" id="status"></div>
        <progress id="progress" max="1" value="0"></progress>
        <video id="player" controls playsinline></video>
        <img class="snap" id="snap" alt="">
      </ha-card>`;
    const root = this.shadowRoot;
    root.querySelectorAll(".period").forEach((b) => (b.onclick = () => {
      this._hours = Number(b.dataset.h);
      this._load();
    }));
    root.getElementById("timelapse").onclick = () => this._timelapse();
    root.getElementById("player").onerror = () => this._status(this._t("noRec"));
    this._markPeriod();
  }

  _markPeriod() {
    this.shadowRoot.querySelectorAll(".period").forEach((b) =>
      b.classList.toggle("on", Number(b.dataset.h) === this._hours));
  }

  _status(text, html = false) {
    const el = this.shadowRoot.getElementById("status");
    if (html) el.innerHTML = text; else el.textContent = text;
  }

  _cameras() {
    const filter = this._cfg.cameras;
    const cams = (this._data && this._data.cameras) || [];
    if (!filter || !filter.length) return cams;
    return cams.filter((c) => filter.includes(c.id) || filter.includes(c.name));
  }

  async _load() {
    if (!this._hass) return;
    this._markPeriod();
    try {
      this._data = await this._api("GET", `timeline?hours=${this._hours}`);
      this._renderTimeline();
    } catch (err) {
      this._status(`${this._t("error")} (${err.message || err.body?.message || err})`);
    }
  }

  _ticks(start, end) {
    const span = end - start;
    const step = span <= 86400 ? 3 * 3600 : span <= 3 * 86400 ? 12 * 3600 : 86400;
    const fmt = span <= 86400
      ? { hour: "2-digit", minute: "2-digit" }
      : span <= 3 * 86400 ? { weekday: "short", hour: "2-digit" } : { weekday: "short", day: "2-digit", month: "2-digit" };
    const locale = this._hass.locale?.language || this._hass.language;
    const offset = new Date().getTimezoneOffset() * 60;
    let t = Math.ceil((start - offset) / step) * step + offset;
    const out = [];
    for (; t < end; t += step) out.push([t, new Date(t * 1000).toLocaleString(locale, fmt)]);
    return out;
  }

  _renderTimeline() {
    const d = this._data;
    const span = d.end - d.start;
    const pct = (ts) => `${Math.max(0, Math.min(100, ((ts - d.start) / span) * 100)).toFixed(3)}%`;
    const now = Date.now() / 1000;
    const locale = this._hass.locale?.language || this._hass.language;
    const when = (ts) => new Date(ts * 1000).toLocaleString(locale, { weekday: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const cams = this._cameras();
    let html = `<div class="scale">${this._ticks(d.start, d.end).map(([t, l]) => `<span style="left:${pct(t)}">${esc(l)}</span>`).join("")}</div>`;
    html += cams.map((c) => {
      const events = c.events.filter((e) => this._cfg.show_rejected || e.confirmed !== false);
      const alarms = events.filter((e) => e.confirmed).length;
      return `<div class="row">
        <div class="name" title="${esc(c.name)}">${esc(c.name)}<small>${events.length} ${this._t("events")} · ${alarms} ${this._t("alarms")}</small></div>
        <div class="track" data-cam="${esc(c.id)}" data-name="${esc(c.name)}">
          ${c.recordings.map(([a, b]) => `<div class="rec" style="left:${pct(a)};width:${(((b - a) / span) * 100).toFixed(3)}%"></div>`).join("")}
          ${events.map((e) => {
            const cls = e.confirmed === null ? "p" : e.confirmed ? "c" : "r";
            const state = e.confirmed === null ? this._t("pending") : e.confirmed ? this._t("alarm") : this._t("rejected");
            const tip = `${when(e.start)} · ${state} · ${(e.description || (e.labels || []).join(", "))}${e.archived ? ` · ☁ ${this._t("cloud")}` : ""}`;
            return `<div class="ev ${cls}${e.archived ? " a" : ""}" style="left:${pct(e.start)}" data-ev="${esc(e.id)}" data-clip="${e.has_clip}" title="${esc(tip)}"></div>`;
          }).join("")}
          ${now > d.start && now < d.end ? `<div class="now" style="left:${pct(now)}"></div>` : ""}
        </div></div>`;
    }).join("") || `<div class="status">${this._t("noCams")}</div>`;
    const box = this.shadowRoot.getElementById("timeline");
    box.innerHTML = html;
    box.querySelectorAll(".ev").forEach((el) => (el.onclick = (ev) => {
      ev.stopPropagation();
      this._openEvent(el.dataset.ev, el.dataset.clip === "true", el.title);
    }));
    box.querySelectorAll(".track").forEach((track) => (track.onclick = (ev) => {
      const r = track.getBoundingClientRect();
      const ts = Math.floor(d.start + ((ev.clientX - r.left) / r.width) * span - 10);
      this._play(`cameras/${track.dataset.cam}/recording/${ts}/60.mp4`,
        `${track.dataset.name}: ${this._t("rec")} ${when(ts)}`);
    }));
  }

  async _openEvent(id, hasClip, text) {
    if (hasClip) return this._play(`events/${id}/clip.mp4`, text);
    const img = this.shadowRoot.getElementById("snap");
    this.shadowRoot.getElementById("player").style.display = "none";
    img.src = await this._signed(`events/${id}/snapshot.jpg`);
    img.style.display = "block";
    this._status(`${text}`);
  }

  async _play(path, text) {
    const video = this.shadowRoot.getElementById("player");
    this.shadowRoot.getElementById("snap").style.display = "none";
    try {
      video.src = await this._signed(path);
      video.style.display = "block";
      this._status(text);
      video.play().catch(() => {});
    } catch (err) {
      this._status(String(err.message || err));
    }
  }

  async _timelapse() {
    const c = this._cfg;
    const progress = this.shadowRoot.getElementById("progress");
    const body = {
      hours: this._hours, mode: c.timelapse_mode, speed: Number(c.timelapse_speed),
      only_confirmed: c.only_confirmed,
    };
    const cams = this._cameras().map((x) => x.id);
    if (c.cameras && c.cameras.length) body.cameras = cams;
    clearTimeout(this._poll);
    try {
      let job = await this._api("POST", "timelapse", body);
      const step = async () => {
        if (job.state === "queued" || job.state === "building") {
          progress.style.display = "block";
          progress.max = job.total || 1;
          progress.value = job.progress || 0;
          this._status(`${this._t("building")} … ${job.progress || 0}/${job.total || "?"}`);
          this._poll = setTimeout(async () => {
            job = await this._api("GET", `timelapse/${job.id}`);
            step();
          }, 2000);
          return;
        }
        progress.style.display = "none";
        if (job.state === "done") this._play(`timelapse/${job.id}.mp4`, `${this._t("timelapse")} · ${job.total} ${this._t("events")}`);
        else if (job.state === "empty") this._status(this._t("empty"));
        else this._status(`${this._t("timelapse")}: ${job.error || job.state}`);
      };
      step();
    } catch (err) {
      progress.style.display = "none";
      this._status(`${this._t("error")} (${err.message || err})`);
    }
  }
}

customElements.define("alcedo-timeline-card", AlcedoTimelineCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "alcedo-timeline-card",
  name: "Alcedo NVR Timeline",
  description: "Timeline of all cameras with alarms, recordings and timelapse.",
  preview: false,
});
