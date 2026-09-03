import {
  AfterViewInit, Component, ElementRef, EventEmitter, Input, OnChanges, OnDestroy,
  Output, SimpleChanges, ViewChild,
} from '@angular/core';
import * as LeafletNS from 'leaflet';
import 'leaflet.markercluster';
import { Stop } from './models';

// leaflet.markercluster არის UMD-პლაგინი: ის *გლობალურ* `L`-ს ამატებს markerClusterGroup-ს.
// `import * as L from 'leaflet'` კი ES-მოდულის namespace-ს აბრუნებს, რომელიც გაყინულია — ამიტომ
// პლაგინის დამატება მასზე ვერ ხვდება და `L.markerClusterGroup is not a function` იჭრება
// ngAfterViewInit-ში. შედეგად რუკაზე *არცერთი* გაჩერება არ ჩნდებოდა (tile-ები ჩანდა, მარკერები — არა).
// ამიტომ კონსტრუქტორებს გლობალური ობიექტიდან ვიღებთ, სადაც პლაგინი მართლა დაჯდა.
type LeafletWithCluster = typeof LeafletNS & {
  markerClusterGroup(options?: LeafletNS.MarkerClusterGroupOptions): LeafletNS.MarkerClusterGroup;
};
const L = ((window as unknown as { L?: LeafletWithCluster }).L ?? LeafletNS) as LeafletWithCluster;

export interface UserPos { lat: number; lon: number; accuracy: number; }

// Leaflet რუკა. აქამდე რუკა/GPS არასწორად მუშაობდა — ამ კომპონენტში სამი კონკრეტული მიზეზია
// გასწორებული:
//   1. კონტეინერს ზომა ხშირად ჯერ არ აქვს, როცა რუკა იქმნება (flex/grid layout, mobile-ზე
//      ჩანართის გადართვა) — Leaflet მაშინ არასწორ ზომას იმახსოვრებს და tile-ები "იჭრება".
//      ამას ResizeObserver + invalidateSize აგვარებს.
//   2. არჩევისას ერთდროულად ეშვებოდა zoomToShowLayer-ის ანიმაცია და setView — ორი ანიმაცია
//      ერთმანეთს ებრძოდა და რუკა შემთხვევით ადგილას ჩერდებოდა. ახლა ერთი გზაა.
//   3. მარკერები ყოველ ngOnChanges-ზე თავიდან იხატებოდა (2,710 მარკერი) — ახლა მხოლოდ მაშინ,
//      როცა თავად სია შეიცვალა.
@Component({
  selector: 'app-map',
  standalone: true,
  template: `<div #host class="host"></div>`,
  styles: [`
    :host { display: block; position: relative; width: 100%; height: 100%; }
    .host { position: absolute; inset: 0; }
  `],
})
export class MapComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() stops: Stop[] = [];
  @Input() selectedId: string | null = null;
  @Input() userPos: UserPos | null = null;
  @Output() stopPicked = new EventEmitter<Stop>();

  @ViewChild('host', { static: true }) host!: ElementRef<HTMLElement>;

  private map?: LeafletNS.Map;
  private cluster?: LeafletNS.MarkerClusterGroup;
  private plain?: LeafletNS.LayerGroup;
  private markers = new Map<string, LeafletNS.CircleMarker>();
  private userMarker?: LeafletNS.CircleMarker;
  private userCircle?: LeafletNS.Circle;
  private ro?: ResizeObserver;
  private drawnFor: Stop[] | null = null;

  ngAfterViewInit(): void {
    this.map = L.map(this.host.nativeElement, {
      center: [41.7151, 44.8271],           // თბილისის ცენტრი
      zoom: 13,
      zoomControl: true,
      preferCanvas: true,                    // 2,710 წრიული მარკერი SVG-ზე ბევრად ნელია
    });

    // OSM-ის სტანდარტული tile-ები — გასაღების გარეშე. CARTO-ს მუქი basemap ახლა API key-ს
    // ითხოვს (tile-ები "API KEY REQUIRED" წარწერით მოდის), ამიტომ ღია tile-ებს ვიღებთ და
    // მუქად CSS-ით ვაქცევთ (.leaflet-tile-pane ფილტრი styles.css-ში). ატრიბუცია სავალდებულოა.
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© OpenStreetMap',
    }).addTo(this.map);

    if (typeof L.markerClusterGroup === 'function') {
      this.cluster = L.markerClusterGroup({
        maxClusterRadius: 60,
        disableClusteringAtZoom: 17,
        showCoverageOnHover: false,
        chunkedLoading: true,                // 2,710 მარკერის დამატება UI-ს რომ არ გააჩეროს
      } as LeafletNS.MarkerClusterGroupOptions);
      this.map.addLayer(this.cluster);
    } else {
      // ჯგუფვის გარეშეც რუკა უნდა მუშაობდეს — ცარიელი რუკა ყველაზე ცუდი შედეგია.
      console.warn('leaflet.markercluster unavailable — falling back to unclustered markers');
      this.plain = L.layerGroup().addTo(this.map);
    }

    // კონტეინერის ზომის ნებისმიერი ცვლილება (layout, ჩანართი, ორიენტაცია) -> გადაზომვა.
    this.ro = new ResizeObserver(() => this.map?.invalidateSize());
    this.ro.observe(this.host.nativeElement);

    this.draw();
    this.syncUser();
    this.focusSelected(false);
  }

  ngOnChanges(ch: SimpleChanges): void {
    if (!this.map) { return; }
    if (ch['stops']) { this.draw(); }
    if (ch['userPos']) { this.syncUser(); }
    if (ch['selectedId']) { this.focusSelected(true); }
  }

  ngOnDestroy(): void {
    this.ro?.disconnect();
    this.map?.remove();
  }

  private draw(): void {
    const group = this.cluster ?? this.plain;
    if (!group || this.drawnFor === this.stops) { return; }
    this.drawnFor = this.stops;
    group.clearLayers();
    this.markers.clear();
    const layers: LeafletNS.CircleMarker[] = [];
    for (const s of this.stops) {
      if (s.lat == null || s.lon == null) { continue; }
      const m = L.circleMarker([s.lat, s.lon], this.style(s.id === this.selectedId));
      m.bindTooltip(s.name, { direction: 'top', offset: [0, -6] });
      m.on('click', () => this.stopPicked.emit(s));
      this.markers.set(s.id, m);
      layers.push(m);
    }
    if (this.cluster) { this.cluster.addLayers(layers); }
    else { layers.forEach(m => this.plain!.addLayer(m)); }
  }

  private style(active: boolean): LeafletNS.CircleMarkerOptions {
    return active
      ? { radius: 8, color: '#e9e9ed', weight: 2, fillColor: '#9184d9', fillOpacity: 1 }
      : { radius: 5, color: '#161826', weight: 1.5, fillColor: '#75798c', fillOpacity: 1 };
  }

  private syncUser(): void {
    if (!this.map) { return; }
    if (!this.userPos) {
      this.userMarker?.remove(); this.userCircle?.remove();
      this.userMarker = this.userCircle = undefined;
      return;
    }
    const { lat, lon, accuracy } = this.userPos;
    // სიზუსტის რადიუსი ცალკე წრეა — თუ GPS სუსტია, მომხმარებელი ხედავს, რომ წერტილი მიახლოებითია.
    if (!this.userCircle) {
      this.userCircle = L.circle([lat, lon], {
        radius: accuracy, color: '#9184d9', weight: 1,
        fillColor: '#9184d9', fillOpacity: 0.12,
      }).addTo(this.map);
    } else {
      this.userCircle.setLatLng([lat, lon]).setRadius(accuracy);
    }
    if (!this.userMarker) {
      this.userMarker = L.circleMarker([lat, lon], {
        radius: 6, color: '#ffffff', weight: 2.5, fillColor: '#9184d9', fillOpacity: 1,
      }).addTo(this.map);
    } else {
      this.userMarker.setLatLng([lat, lon]);
    }
    this.userMarker.bringToFront();
  }

  /** მომხმარებლის პოზიციაზე გადასვლა — „მდებარეობა" ღილაკიდან. */
  flyToUser(): void {
    if (this.map && this.userPos) {
      this.map.setView([this.userPos.lat, this.userPos.lon], 16, { animate: true });
    }
  }

  private focusSelected(animate: boolean): void {
    if (!this.map) { return; }
    this.markers.forEach((m, id) => m.setStyle(this.style(id === this.selectedId)));
    if (!this.selectedId) { return; }
    const marker = this.markers.get(this.selectedId);
    const stop = this.stops.find(s => s.id === this.selectedId);
    if (!stop) { return; }

    const target: LeafletNS.LatLngExpression = [stop.lat, stop.lon];
    const zoom = Math.max(this.map.getZoom(), 16);
    if (marker && this.cluster?.hasLayer(marker)) {
      // zoomToShowLayer თავად ამოძრავებს რუკას; setView-ს *არ* ვუშვებთ პარალელურად.
      this.cluster.zoomToShowLayer(marker, () => marker.bringToFront());
    } else {
      this.map.setView(target, zoom, { animate });
    }
  }
}
