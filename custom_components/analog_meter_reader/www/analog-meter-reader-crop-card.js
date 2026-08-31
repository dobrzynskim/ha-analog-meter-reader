/**
 * Karta Lovelace do wizualnej kalibracji ramki przycięcia (analog_meter_reader)
 * - przeciągnij prostokąt bezpośrednio na zdjęciu, zamiast odczytywać piksele
 *   z siatki współrzędnych i wpisywać je ręcznie (jak w config_flow, który nie
 *   może pokazać interaktywnego canvasu - ograniczenie formularzy HA).
 *
 * Konfiguracja karty (YAML/UI):
 *   type: custom:analog-meter-reader-crop-card
 *   camera_entity: camera.wodomierz_ostatnie_zdjecie
 *   reading_entity: sensor.wodomierz   # opcjonalnie - pokazuje aktualny
 *                                       # odczyt w tej samej karcie, żeby nie
 *                                       # trzeba było dokładać osobnej karty
 *                                       # tylko po to, żeby go zobaczyć.
 *
 * Serwis analog_meter_reader.set_crop_box celuje w encję (target: entity,
 * domain: camera) - karta woła go wprost na podanej camera_entity, bez
 * potrzeby rozwiązywania device_id.
 */

const HANDLES = ["nw", "ne", "sw", "se"];

class AnalogMeterReaderCropCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.camera_entity) {
      throw new Error(
        "analog-meter-reader-crop-card: podaj camera_entity, np. camera.wodomierz_ostatnie_zdjecie"
      );
    }
    this._config = config;
    this._box = null; // {left, top, right, bottom} w NATURALNYCH pikselach zdjęcia
    this._boxInitialized = false;
    this._dragMode = null; // null | 'new' | 'move' | 'nw' | 'ne' | 'sw' | 'se'
    this._dragOriginBox = null;
    this._dragOriginPoint = null;
    this._naturalW = 0;
    this._naturalH = 0;
    this._saving = false;
    if (!this._built) {
      this._build();
    }
  }

  set hass(hass) {
    const previousHass = this._hass;
    this._hass = hass;
    if (!this._built) return;

    const state = hass.states[this._config.camera_entity];
    if (!state) {
      this._setStatus(`Nie znaleziono encji ${this._config.camera_entity}`, true);
      return;
    }

    const picture = state.attributes.entity_picture;
    if (picture && this._img.getAttribute("data-src") !== picture) {
      this._img.setAttribute("data-src", picture);
      this._img.src = hass.hassUrl ? hass.hassUrl(picture) : picture;
    }

    if (this._config.reading_entity) {
      const readingState = hass.states[this._config.reading_entity];
      if (readingState) {
        const unit = readingState.attributes.unit_of_measurement || "";
        this._readingEl.hidden = false;
        this._readingEl.textContent = `Odczyt: ${readingState.state} ${unit}`.trim();
      }
    }

    if (!this._boxInitialized) {
      const { crop_left, crop_top, crop_right, crop_bottom } = state.attributes;
      if (
        crop_left !== undefined &&
        crop_top !== undefined &&
        crop_right !== undefined &&
        crop_bottom !== undefined
      ) {
        this._box = { left: crop_left, top: crop_top, right: crop_right, bottom: crop_bottom };
        this._boxInitialized = true;
        this._updateOverlay();
      }
    }

    // Odśwież status tylko gdy faktycznie coś się zmieniło - unikamy migotania
    // komunikatu o błędzie przy każdym tyknięciu hass (kilka razy/s).
    if (!previousHass) {
      this._clearStatusIfIdle();
    }
  }

  _build() {
    this._built = true;
    const shadow = this.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 16px; }
        .stage {
          position: relative;
          width: 100%;
          overflow: hidden;
          border-radius: 8px;
          background: var(--divider-color, #666);
          touch-action: none;
          user-select: none;
        }
        .stage img { display: block; width: 100%; height: auto; }
        .rect {
          position: absolute;
          border: 2px solid #ff5252;
          box-shadow: 0 0 0 1000px rgba(0, 0, 0, 0.35);
          box-sizing: border-box;
          cursor: move;
        }
        .handle {
          position: absolute;
          width: 16px;
          height: 16px;
          margin: -8px;
          border-radius: 50%;
          background: #ff5252;
          border: 2px solid white;
          box-sizing: border-box;
        }
        .handle.nw { top: 0; left: 0; cursor: nwse-resize; }
        .handle.ne { top: 0; left: 100%; cursor: nesw-resize; }
        .handle.sw { top: 100%; left: 0; cursor: nesw-resize; }
        .handle.se { top: 100%; left: 100%; cursor: nwse-resize; }
        .row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-top: 12px;
          flex-wrap: wrap;
        }
        .readout { font-family: monospace; font-size: 0.9em; color: var(--secondary-text-color); }
        .status { font-size: 0.9em; margin-top: 4px; min-height: 1.2em; }
        .status.error { color: var(--error-color, #db4437); }
        .status.ok { color: var(--success-color, #43a047); }
        button {
          background: var(--primary-color);
          color: var(--text-primary-color, white);
          border: none;
          border-radius: 4px;
          padding: 8px 16px;
          font-size: 0.95em;
          cursor: pointer;
        }
        button:disabled { opacity: 0.5; cursor: default; }
        .preview-section { margin-top: 16px; }
        .preview-label {
          font-size: 0.9em;
          color: var(--secondary-text-color);
          margin-bottom: 4px;
        }
        .preview {
          overflow: hidden;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          /* Zapasowe ograniczenie - normalnie _updatePreview() dobiera zoom
             tak, żeby szerokość i tak już mieściła się w karcie, bez tego
             CSS ucinałoby tylko szerokość (nie wysokość) i podgląd wyglądał
             na rozciągnięty/zniekształcony zamiast po prostu mniejszy. */
          max-width: 100%;
        }
        .preview img { display: block; max-width: none; }
        .reading {
          font-size: 1.1em;
          font-weight: 600;
          margin-bottom: 12px;
        }
      </style>
      <ha-card header="Kalibracja ramki przycięcia">
        <div class="reading" hidden></div>
        <div class="stage">
          <img alt="Zdjęcie z kamery licznika" />
          <div class="rect" hidden>
            <div class="handle nw" data-handle="nw"></div>
            <div class="handle ne" data-handle="ne"></div>
            <div class="handle sw" data-handle="sw"></div>
            <div class="handle se" data-handle="se"></div>
          </div>
        </div>
        <div class="row">
          <span class="readout"></span>
          <button type="button" class="save">Zapisz ramkę</button>
        </div>
        <div class="status"></div>
        <div class="preview-section" hidden>
          <div class="preview-label">Podgląd przycięcia (tak, jak zobaczy je AI):</div>
          <div class="preview"><img alt="Podgląd przycięcia" /></div>
        </div>
      </ha-card>
    `;

    this._stage = shadow.querySelector(".stage");
    this._img = shadow.querySelector(".stage img");
    this._rect = shadow.querySelector(".rect");
    this._readout = shadow.querySelector(".readout");
    this._statusEl = shadow.querySelector(".status");
    this._saveButton = shadow.querySelector(".save");
    this._previewSection = shadow.querySelector(".preview-section");
    this._previewImg = shadow.querySelector(".preview img");
    this._readingEl = shadow.querySelector(".reading");

    this._img.addEventListener("load", () => {
      this._naturalW = this._img.naturalWidth;
      this._naturalH = this._img.naturalHeight;
      if (!this._boxInitialized) {
        // Brak zapisanej ramki jeszcze (pierwsze uruchomienie) - zaproponuj
        // środek zdjęcia jako punkt startowy, żeby uchwyty od razu były widoczne.
        this._box = {
          left: Math.round(this._naturalW * 0.25),
          top: Math.round(this._naturalH * 0.4),
          right: Math.round(this._naturalW * 0.75),
          bottom: Math.round(this._naturalH * 0.6),
        };
      }
      this._updateOverlay();
    });

    this._stage.addEventListener("pointerdown", (e) => this._onPointerDown(e));
    this._stage.addEventListener("pointermove", (e) => this._onPointerMove(e));
    this._stage.addEventListener("pointerup", (e) => this._onPointerUp(e));
    this._stage.addEventListener("pointercancel", (e) => this._onPointerUp(e));
    this._saveButton.addEventListener("click", () => this._save());
  }

  // --- geometria: naturalne px (prawda) <-> wyświetlane px (na ekranie) ---

  _displayScale() {
    const stageRect = this._stage.getBoundingClientRect();
    if (!this._naturalW || !stageRect.width) return 1;
    return this._naturalW / stageRect.width;
  }

  _clientToNatural(clientX, clientY) {
    const stageRect = this._stage.getBoundingClientRect();
    const scale = this._displayScale();
    const x = Math.min(Math.max(clientX - stageRect.left, 0), stageRect.width) * scale;
    const y = Math.min(Math.max(clientY - stageRect.top, 0), stageRect.height) * scale;
    return [Math.round(x), Math.round(y)];
  }

  // --- interakcja ---

  _onPointerDown(e) {
    if (!this._box) return;
    e.preventDefault();
    this._stage.setPointerCapture(e.pointerId);
    const handle = e.target && e.target.dataset ? e.target.dataset.handle : null;
    const [nx, ny] = this._clientToNatural(e.clientX, e.clientY);

    if (handle) {
      this._dragMode = handle;
    } else if (this._pointInsideBox(nx, ny)) {
      this._dragMode = "move";
    } else {
      this._dragMode = "new";
      this._box = { left: nx, top: ny, right: nx, bottom: ny };
    }
    this._dragOriginBox = { ...this._box };
    this._dragOriginPoint = [nx, ny];
    this._updateOverlay();
  }

  _onPointerMove(e) {
    if (!this._dragMode) return;
    e.preventDefault();
    const [nx, ny] = this._clientToNatural(e.clientX, e.clientY);
    const [ox, oy] = this._dragOriginPoint;
    const start = this._dragOriginBox;

    if (this._dragMode === "new") {
      this._box = {
        left: Math.min(ox, nx),
        top: Math.min(oy, ny),
        right: Math.max(ox, nx),
        bottom: Math.max(oy, ny),
      };
    } else if (this._dragMode === "move") {
      const dx = nx - ox;
      const dy = ny - oy;
      const w = start.right - start.left;
      const h = start.bottom - start.top;
      let left = start.left + dx;
      let top = start.top + dy;
      left = Math.min(Math.max(left, 0), Math.max(this._naturalW - w, 0));
      top = Math.min(Math.max(top, 0), Math.max(this._naturalH - h, 0));
      this._box = { left, top, right: left + w, bottom: top + h };
    } else {
      // resize z jednego z 4 rogów
      const box = { ...start };
      if (this._dragMode.includes("n")) box.top = ny;
      if (this._dragMode.includes("s")) box.bottom = ny;
      if (this._dragMode.includes("w")) box.left = nx;
      if (this._dragMode.includes("e")) box.right = nx;
      this._box = {
        left: Math.min(box.left, box.right),
        right: Math.max(box.left, box.right),
        top: Math.min(box.top, box.bottom),
        bottom: Math.max(box.top, box.bottom),
      };
    }
    this._updateOverlay();
  }

  _onPointerUp(e) {
    if (!this._dragMode) return;
    try {
      this._stage.releasePointerCapture(e.pointerId);
    } catch (err) {
      // capture mogło już wygasnąć - nic nie robimy
    }
    this._dragMode = null;
    this._dragOriginBox = null;
    this._dragOriginPoint = null;
  }

  _pointInsideBox(nx, ny) {
    const b = this._box;
    return nx >= b.left && nx <= b.right && ny >= b.top && ny <= b.bottom;
  }

  // --- render ---

  _updateOverlay() {
    if (!this._box || !this._naturalW) return;
    const scale = this._displayScale();
    const b = this._box;
    this._rect.hidden = false;
    this._rect.style.left = `${b.left / scale}px`;
    this._rect.style.top = `${b.top / scale}px`;
    this._rect.style.width = `${(b.right - b.left) / scale}px`;
    this._rect.style.height = `${(b.bottom - b.top) / scale}px`;

    this._readout.textContent = `L:${b.left} T:${b.top} R:${b.right} B:${b.bottom} (${b.right - b.left}×${b.bottom - b.top}px)`;

    this._updatePreview();
  }

  _updatePreview() {
    const b = this._box;
    const w = b.right - b.left;
    const h = b.bottom - b.top;
    if (!w || !h || !this._img.src) {
      this._previewSection.hidden = true;
      return;
    }
    this._previewSection.hidden = false;

    // Dobierz zoom tak, żeby SZEROKOŚĆ podglądu zmieściła się w karcie
    // (np. na telefonie) - wysokość skaluje się tym samym współczynnikiem,
    // więc proporcje zostają zachowane. Sztywne ×4 przy wąskiej ramce na
    // szerokim ekranie i tak dawało nieproporcjonalnie duży podgląd; na
    // wąskim ekranie CSS ucinał tylko szerokość (max-width), nie wysokość,
    // co wyglądało jak rozciągnięcie zamiast zwykłego pomniejszenia.
    const maxZoom = 4;
    const containerWidth =
      this._previewSection.clientWidth || this._stage.clientWidth || w * maxZoom;
    const zoom = Math.max(1, Math.min(maxZoom, containerWidth / w));

    this._previewImg.src = this._img.src;
    this._previewImg.style.width = `${this._naturalW * zoom}px`;
    this._previewImg.style.marginLeft = `-${b.left * zoom}px`;
    this._previewImg.style.marginTop = `-${b.top * zoom}px`;
    this._previewImg.parentElement.style.width = `${w * zoom}px`;
    this._previewImg.parentElement.style.height = `${h * zoom}px`;
  }

  _setStatus(message, isError) {
    this._statusEl.textContent = message;
    this._statusEl.className = `status ${isError ? "error" : "ok"}`;
  }

  _clearStatusIfIdle() {
    if (!this._saving) {
      this._statusEl.textContent = "";
      this._statusEl.className = "status";
    }
  }

  async _save() {
    if (!this._box || this._saving) return;
    const b = this._box;
    if (b.right <= b.left || b.bottom <= b.top) {
      this._setStatus("Ramka jest pusta - przeciągnij prostokąt na zdjęciu.", true);
      return;
    }

    this._saving = true;
    this._saveButton.disabled = true;
    this._setStatus("Zapisywanie...", false);
    try {
      await this._hass.callService("analog_meter_reader", "set_crop_box", {
        entity_id: this._config.camera_entity,
        crop_left: b.left,
        crop_top: b.top,
        crop_right: b.right,
        crop_bottom: b.bottom,
      });
      this._setStatus(
        "Zapisano. Nowa ramka zastosuje się od następnego cyklu (albo przycisku „Wymuś odczyt teraz”).",
        false
      );
    } catch (err) {
      this._setStatus(`Błąd zapisu: ${err.message || err}`, true);
    } finally {
      this._saving = false;
      this._saveButton.disabled = false;
    }
  }

  getCardSize() {
    return 6;
  }
}

customElements.define("analog-meter-reader-crop-card", AnalogMeterReaderCropCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "analog-meter-reader-crop-card",
  name: "Analog Meter Reader - kalibracja ramki",
  description: "Wizualna kalibracja ramki przycięcia przeciąganiem prostokąta na zdjęciu.",
});
