import {
  Component, AfterViewInit, ElementRef, EventEmitter, Input, Output, ViewChild, OnChanges
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import * as L from 'leaflet';
import { Stop } from './models';
import { distanceMeters } from './stop.service';

// გაჩერების არჩევა: სახელით ძებნა + Leaflet რუკა + „ჩემთან ახლოს" (GPS).
@Component({
  selector: 'app-stop-picker',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="search-row">
      <div class="search">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <circle cx="7" cy="7" r="5" stroke="#5b6b67" stroke-width="2"></circle>
          <line x1="11" y1="11" x2="15" y2="15" stroke="#5b6b67" stroke-width="2" stroke-linecap="round"></line>
        </svg>
        <input type="text" [(ngModel)]="query" (ngModelChange)="onQuery()" placeholder="გაჩერების ძებნა" />
      </div>
      <button class="near" type="button" (click)="locate()" [disabled]="locating">
        📍 {{ locating ? '…' : 'ახლოს' }}
      </button>
    </div>
    <p class="geo-error" *ngIf="geoError">{{ geoError }}</p>

    <div class="map-wrap">
      <div #map class="map"></div>
      <div class="count-chip">{{ stops.length }} გაჩერება</div>
    </div>

    <ul class="stop-list">
      <li *ngFor="let s of filtered" [class.active]="s.id === selectedId" (click)="select(s)">
        <span class="pin" [class.on]="s.id === selectedId"><i></i></span>
        <span class="info">
          <span class="name">{{ s.name }}</span>
          <span class="meta">{{ s.routes.length }} მარშრუტი</span>
        </span>
        <span class="check" *ngIf="s.id === selectedId">✓</span>
      </li>
      <li class="none" *ngIf="!filtered.length">ვერ მოიძებნა</li>
    </ul>
  `,
  styles: [`
    .search-row { display: flex; gap: 10px; margin-bottom: 12px; }
    .search { flex: 1; display: flex; align-items: center; gap: 9px; background: rgba(255,255,255,0.8);
              border: 1px solid var(--card-border); border-radius: 16px; padding: 12px 14px;
              box-shadow: 0 1px 0 rgba(255,255,255,0.85) inset, 0 6px 16px -10px rgba(20,60,55,0.4); }
    .search svg { flex: none; }
    .search input { flex: 1; border: 0; background: transparent; outline: none;
                    font: 500 14px var(--geo); color: var(--ink); min-width: 0; }
    .search input::placeholder { color: var(--faint); }
    .near { white-space: nowrap; border: 1px solid rgba(255,255,255,0.9); cursor: pointer;
            background: linear-gradient(#fff, #eef5f3); color: var(--green-ink);
            font: 600 13px var(--geo); border-radius: 16px; padding: 0 15px;
            box-shadow: 0 1px 0 rgba(255,255,255,0.9) inset, 0 6px 16px -10px rgba(20,60,55,0.4); }
    .near:disabled { opacity: 0.55; }
    .geo-error { color: #c0392b; margin: 0 0 0.5rem; font-size: 0.85rem; }

    .map-wrap { position: relative; margin-bottom: 16px; }
    .map { height: 200px; border-radius: 24px; overflow: hidden;
           box-shadow: 0 12px 26px -14px rgba(20,60,55,0.45); border: 1px solid rgba(255,255,255,0.7); }
    .count-chip { position: absolute; left: 12px; bottom: 12px; z-index: 500;
                  background: rgba(255,255,255,0.92); border-radius: 11px; padding: 6px 11px;
                  font: 600 11px var(--geo); color: var(--ink2); box-shadow: 0 4px 10px rgba(0,0,0,0.12); }

    .stop-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px;
                 max-height: 232px; overflow-y: auto; }
    .stop-list li { display: flex; align-items: center; gap: 12px; cursor: pointer;
                    background: var(--card-soft); border: 1px solid rgba(255,255,255,0.9);
                    border-radius: 18px; padding: 13px 15px; }
    .stop-list li.active { background: linear-gradient(#fff, #f1faf7); border: 1.5px solid var(--green-border);
                           box-shadow: 0 10px 22px -14px rgba(0,150,120,0.55); }
    .pin { flex: none; width: 34px; height: 34px; border-radius: 11px; background: #e7eeec;
           display: flex; align-items: center; justify-content: center; }
    .pin i { width: 9px; height: 9px; border-radius: 50% 50% 50% 0; background: #8aa3a0;
             transform: rotate(45deg); display: block; }
    .pin.on { background: var(--grad-green); box-shadow: 0 1px 0 rgba(255,255,255,0.5) inset; }
    .pin.on i { background: #fff; }
    .info { flex: 1; min-width: 0; display: flex; flex-direction: column; }
    .name { font: 600 15px var(--geo); color: var(--ink2); }
    .active .name { font-weight: 700; color: var(--ink); }
    .meta { font: 500 12px var(--geo); color: var(--muted2); margin-top: 2px; }
    .check { font: 700 13px var(--mono); color: var(--green2); }
    .none { color: var(--muted2); cursor: default; justify-content: center; }
  `]
})
export class StopPickerComponent implements AfterViewInit, OnChanges {
  @Input() stops: Stop[] = [];
  @Output() stopSelected = new EventEmitter<Stop>();
  @ViewChild('map') mapEl!: ElementRef<HTMLElement>;

  query = '';
  filtered: Stop[] = [];
  selectedId: string | null = null;
  locating = false;
  geoError = '';

  private map?: L.Map;
  private markers = new Map<string, L.CircleMarker>();

  ngOnChanges(): void {
    this.onQuery();
    if (this.map) { this.drawMarkers(); }
  }

  ngAfterViewInit(): void {
    // თბილისზე ცენტრირებული რუკა, უფასო OSM tile-ები (API key-ის გარეშე).
    this.map = L.map(this.mapEl.nativeElement, { attributionControl: false }).setView([41.7151, 44.8271], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(this.map);
    this.drawMarkers();
  }

  onQuery(): void {
    const q = this.query.trim().toLowerCase();
    this.filtered = q ? this.stops.filter(s => s.name.toLowerCase().includes(q)) : [...this.stops];
  }

  private drawMarkers(): void {
    if (!this.map) { return; }
    this.markers.forEach(m => m.remove());
    this.markers.clear();
    for (const s of this.stops) {
      const m = L.circleMarker([s.lat, s.lon], this.markerStyle(s.id === this.selectedId))
        .addTo(this.map!).bindTooltip(s.name);
      m.on('click', () => this.select(s));
      this.markers.set(s.id, m);
    }
  }

  private markerStyle(active: boolean): L.CircleMarkerOptions {
    // არჩეული — მუქი/დიდი მწვანე; დანარჩენი — ღია მწვანე (palette-ის ფერები).
    return { radius: active ? 9 : 6, color: '#fff', weight: active ? 3 : 2,
             fillColor: active ? '#009d7d' : '#00b38b', fillOpacity: 1 };
  }

  select(s: Stop): void {
    this.selectedId = s.id;
    this.markers.forEach((m, id) => m.setStyle(this.markerStyle(id === s.id)));
    this.map?.panTo([s.lat, s.lon]);
    this.stopSelected.emit(s);
  }

  locate(): void {
    if (!navigator.geolocation) { this.geoError = 'ბრაუზერი არ უჭერს მხარს გეოლოკაციას.'; return; }
    this.locating = true;
    this.geoError = '';
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        this.locating = false;
        const { latitude, longitude } = pos.coords;
        const nearest = this.nearestStop(latitude, longitude);
        if (nearest) { this.select(nearest); this.map?.setView([nearest.lat, nearest.lon], 15); }
      },
      () => { this.locating = false; this.geoError = 'ლოკაცია ვერ მივიღეთ.'; },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  }

  private nearestStop(lat: number, lon: number): Stop | null {
    let best: Stop | null = null;
    let bestD = Infinity;
    for (const s of this.stops) {
      const d = distanceMeters(lat, lon, s.lat, s.lon);
      if (d < bestD) { bestD = d; best = s; }
    }
    return best;
  }
}
