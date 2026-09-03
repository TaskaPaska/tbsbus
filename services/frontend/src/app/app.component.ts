import { Component, OnDestroy, OnInit, ViewChild, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MapComponent, UserPos } from './map.component';
import { ArrivalRowsComponent } from './arrival-rows.component';
import { StopService, distanceMeters } from './stop.service';
import { ArrivalsStore } from './arrivals.store';
import { FavoritesService } from './favorites.service';
import { I18nService, Lang } from './i18n';
import { Stop } from './models';

type Tab = 'nearby' | 'fav';

// სიაში ერთდროულად რამდენ ბარათს ვხატავთ. ქალაქში 2,710 გაჩერებაა — ყველას ჩვენება
// უაზროდ ანელებს UI-ს, განსაკუთრებით ტელეფონზე.
const MAX_CARDS = 30;
// რამდენ გაჩერებას ვთხოვთ პროგნოზს ავტომატურად. თითო მოთხოვნა ცოცხალი TTC-ის call-ია,
// ამიტომ მხოლოდ სიის თავს ვტვირთავთ (დანარჩენი — არჩევისას).
const PREFETCH = 4;
const REFRESH_MS = 30_000;

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, MapComponent, ArrivalRowsComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css',
})
export class AppComponent implements OnInit, OnDestroy {
  readonly i18n = inject(I18nService);
  readonly favorites = inject(FavoritesService);
  readonly store = inject(ArrivalsStore);
  private readonly api = inject(StopService);

  @ViewChild(MapComponent) mapCmp?: MapComponent;

  stops: Stop[] = [];
  visible: Stop[] = [];
  selected: Stop | null = null;

  query = '';
  tab: Tab = 'nearby';
  userPos: UserPos | null = null;
  locating = false;
  geoError = '';
  loadError = '';
  clock = '';
  showNote = true;

  private timer?: number;

  ngOnInit(): void {
    this.api.getStops().subscribe({
      next: (res) => { this.stops = res.stops ?? []; this.refresh(); },
      error: () => { this.loadError = this.i18n.t().loadStopsError; },
    });
    this.tick();
    this.timer = window.setInterval(() => {
      this.tick();
      // არჩეული გაჩერება ცოცხალი უნდა იყოს; დანარჩენს ქეში უვადოდ არ ანახლებს.
      if (this.selected) { this.store.request(this.selected.id, true); }
    }, REFRESH_MS);
  }

  ngOnDestroy(): void {
    if (this.timer) { clearInterval(this.timer); }
  }

  private tick(): void {
    this.clock = new Date().toLocaleTimeString(this.i18n.lang() === 'ka' ? 'ka-GE' : 'en-GB',
      { hour: '2-digit', minute: '2-digit' });
  }

  setLang(l: Lang): void {
    this.i18n.set(l);
    this.tick();
  }

  setTab(t: Tab): void {
    this.tab = t;
    this.refresh();
  }

  onQuery(): void { this.refresh(); }

  /** სიის გადათვლა — ფილტრი, დალაგება, და თავის რამდენიმე ბარათის პროგნოზის წინასწარ ჩატვირთვა. */
  refresh(): void {
    const q = this.query.trim().toLowerCase();
    let list = this.stops;

    if (this.tab === 'fav') {
      list = list.filter(s => this.favorites.has(s.id));
    }
    if (q) {
      list = list.filter(s =>
        s.name.toLowerCase().includes(q) ||
        (s.routes ?? []).some(r => r.toLowerCase().startsWith(q)));
    }

    // მდებარეობა თუ ვიცით — უახლოესები წინ. ეს არის "ახლოს" ჩანართის მთელი აზრი; ადრე სია
    // თავისი თავდაპირველი რიგით რჩებოდა და მხოლოდ ერთი გაჩერება ირჩეოდა.
    if (this.userPos) {
      const { lat, lon } = this.userPos;
      list = [...list].sort((a, b) =>
        distanceMeters(lat, lon, a.lat, a.lon) - distanceMeters(lat, lon, b.lat, b.lon));
    } else if (q) {
      list = [...list].sort((a, b) => a.name.localeCompare(b.name));
    }

    this.visible = list.slice(0, MAX_CARDS);
    for (const s of this.visible.slice(0, PREFETCH)) { this.store.request(s.id); }
  }

  select(s: Stop): void {
    this.selected = s;
    this.store.request(s.id);
  }

  closeDetail(): void { this.selected = null; }

  toggleFav(s: Stop, ev: Event): void {
    ev.stopPropagation();
    this.favorites.toggle(s.id);
    if (this.tab === 'fav') { this.refresh(); }
  }

  refreshSelected(): void {
    if (this.selected) { this.store.request(this.selected.id, true); }
  }

  trackStop = (_: number, s: Stop) => s.id;

  distanceLabel(s: Stop): string {
    if (!this.userPos) { return ''; }
    return this.i18n.distance(distanceMeters(this.userPos.lat, this.userPos.lon, s.lat, s.lon));
  }

  meta(s: Stop): string {
    const t = this.i18n.t();
    const parts: string[] = [];
    const d = this.distanceLabel(s);
    if (d) { parts.push(d); }
    if (s.routes?.length) { parts.push(`${s.routes.length} ${t.routes}`); }
    return parts.join(' · ');
  }

  locate(): void {
    const t = this.i18n.t();
    if (!navigator.geolocation) { this.geoError = t.geoUnsupported; return; }
    this.locating = true;
    this.geoError = '';
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        this.locating = false;
        this.userPos = {
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy: pos.coords.accuracy ?? 50,
        };
        this.tab = 'nearby';
        this.refresh();
        this.mapCmp?.flyToUser();
      },
      (err) => {
        this.locating = false;
        // კონკრეტული მიზეზი — ადრე ყველა შეცდომა ერთ ზოგად ტექსტს აჩვენებდა და
        // "უარყოფილი წვდომა" ვერ განირჩეოდა "ვერ დავადგინე"-სგან.
        this.geoError =
          err.code === err.PERMISSION_DENIED ? t.geoDenied :
          err.code === err.TIMEOUT ? t.geoTimeout : t.geoUnavailable;
      },
      // enableHighAccuracy=false უფრო სწრაფად და საიმედოდ პასუხობს დესკტოპზე (Wi-Fi/IP),
      // 15წმ ლიმიტით და 1 წუთის ქეშირებული პოზიციის დაშვებით.
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 },
    );
  }
}
