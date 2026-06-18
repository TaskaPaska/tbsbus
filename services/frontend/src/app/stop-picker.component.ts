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
    <div class="picker">
      <input class="search" type="text" [(ngModel)]="query" (ngModelChange)="onQuery()"
             placeholder="გაჩერების ძებნა სახელით…" />
      <button class="near" type="button" (click)="locate()" [disabled]="locating">
        {{ locating ? '…' : '📍 ჩემთან ახლოს' }}
      </button>
    </div>
    <p class="geo-error" *ngIf="geoError">{{ geoError }}</p>

    <div #map class="map"></div>

    <ul class="stop-list">
      <li *ngFor="let s of filtered" [class.active]="s.id === selectedId" (click)="select(s)">
        <span class="name">{{ s.name }}</span>
        <span class="meta">{{ s.routes.length }} მარშრუტი</span>
      </li>
      <li class="none" *ngIf="!filtered.length">ვერ მოიძებნა</li>
    </ul>
  `,
  styles: [`
    .picker { display: flex; gap: 0.5rem; margin-bottom: 0.5rem; }
    .search { flex: 1; padding: 0.55rem 0.7rem; border: 1px solid #ccc; border-radius: 8px; font-size: 1rem; }
    .near { white-space: nowrap; border: 1px solid #00B38B; background: #fff; color: #00805f;
            border-radius: 8px; padding: 0 0.7rem; cursor: pointer; }
    .near:disabled { opacity: 0.5; }
    .geo-error { color: #c0392b; margin: 0 0 0.5rem; font-size: 0.85rem; }
    .map { height: 260px; border-radius: 10px; overflow: hidden; margin-bottom: 0.75rem; }
    .stop-list { list-style: none; margin: 0; padding: 0; max-height: 220px; overflow-y: auto;
                 border: 1px solid #eee; border-radius: 10px; }
    .stop-list li { display: flex; justify-content: space-between; align-items: center;
                    padding: 0.6rem 0.8rem; border-bottom: 1px solid #f0f0f0; cursor: pointer; }
    .stop-list li:last-child { border-bottom: 0; }
    .stop-list li.active { background: #e8f8f3; }
    .stop-list li:hover { background: #f6f6f6; }
    .name { font-weight: 500; }
    .meta { color: #888; font-size: 0.8rem; }
    .none { color: #888; cursor: default; justify-content: center; }
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
    return { radius: active ? 9 : 6, color: '#fff', weight: 2,
             fillColor: active ? '#c0392b' : '#00B38B', fillOpacity: 1 };
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
