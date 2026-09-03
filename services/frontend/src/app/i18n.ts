import { Injectable, signal } from '@angular/core';

// ორენოვანი ტექსტები. ქართული ნაგულისხმევია (ადგილობრივი აპია), ინგლისური — არჩევითი,
// არჩევანი localStorage-ში ინახება, რომ ყოველ გახსნაზე თავიდან არ ირჩეოდეს.
export type Lang = 'ka' | 'en';

export interface Strings {
  tagline: string;
  search: string;
  nearby: string;
  favorites: string;
  locate: string;
  locating: string;
  stopWord: string;
  back: string;
  updated: string;
  min: string;
  now: string;
  routes: string;
  stops: string;
  noArrivals: string;
  loading: string;
  loadStopsError: string;
  predictError: string;
  geoUnsupported: string;
  geoDenied: string;
  geoUnavailable: string;
  geoTimeout: string;
  youAreHere: string;
  noFavorites: string;
  noFavoritesHint: string;
  noResults: string;
  addFavorite: string;
  removeFavorite: string;
  laterThanOfficial: string;
  earlierThanOfficial: string;
  matchesOfficial: string;
  officialShort: string;
  scheduleShort: string;
  modelNote: string;
  modelNoteShort: string;
  refresh: string;
  nearYou: string;
  away: string;
  m: string;
  km: string;
}

const KA: Strings = {
  tagline: 'ავტობუსის პროგნოზი',
  search: 'გაჩერების ძებნა',
  nearby: 'ახლოს',
  favorites: 'რჩეული',
  locate: 'მდებარეობა',
  locating: 'ვეძებთ…',
  stopWord: 'გაჩერება',
  back: 'უკან',
  updated: 'განახლდა',
  min: 'წთ',
  now: 'ახლა',
  routes: 'მარშრუტი',
  stops: 'გაჩერება',
  noArrivals: 'ამ გაჩერებაზე ახლა realtime რეისი არ ჩანს.',
  loading: 'იტვირთება…',
  loadStopsError: 'გაჩერებების სია ვერ ჩაიტვირთა.',
  predictError: 'პროგნოზი ვერ ჩაიტვირთა.',
  geoUnsupported: 'ბრაუზერს გეოლოკაცია არ აქვს.',
  geoDenied: 'მდებარეობაზე წვდომა უარყოფილია — ჩართეთ ბრაუზერის პარამეტრებში.',
  geoUnavailable: 'მდებარეობა ვერ დადგინდა.',
  geoTimeout: 'მდებარეობის დადგენა დიდხანს გაგრძელდა. სცადეთ ხელახლა.',
  youAreHere: 'თქვენ აქ ხართ',
  noFavorites: 'რჩეული ჯერ არ გაქვთ.',
  noFavoritesHint: 'გაჩერების გვერდით ★-ს დააჭირეთ, რომ აქ გამოჩნდეს.',
  noResults: 'ვერაფერი მოიძებნა.',
  addFavorite: 'რჩეულებში დამატება',
  removeFavorite: 'რჩეულებიდან მოშორება',
  laterThanOfficial: 'წუთით გვიან, ვიდრე ოფიციალური',
  earlierThanOfficial: 'წუთით ადრე, ვიდრე ოფიციალური',
  matchesOfficial: 'ოფიციალურს ემთხვევა',
  officialShort: 'ოფიციალური',
  scheduleShort: 'განრიგით',
  modelNote: 'დროები ჩვენი მოდელის პროგნოზია — შეგროვულ ისტორიულ მონაცემებზეა ნასწავლი, '
    + 'და არა TTC-ის ოფიციალური მაჩვენებელი. ქვეშ ნაჩვენებია, რამდენად სცდება ოფიციალურს.',
  modelNoteShort: 'მოდელის პროგნოზი, არა ოფიციალური',
  refresh: 'განახლება',
  nearYou: 'თქვენთან ახლოს',
  away: 'მოშორებით',
  m: 'მ',
  km: 'კმ',
};

const EN: Strings = {
  tagline: 'Bus arrival predictions',
  search: 'Search stops',
  nearby: 'Nearby',
  favorites: 'Favorites',
  locate: 'Locate me',
  locating: 'Locating…',
  stopWord: 'Stop',
  back: 'Back',
  updated: 'Updated',
  min: 'min',
  now: 'now',
  routes: 'routes',
  stops: 'stops',
  noArrivals: 'No realtime buses showing at this stop right now.',
  loading: 'Loading…',
  loadStopsError: 'Could not load the stop list.',
  predictError: 'Could not load predictions.',
  geoUnsupported: 'This browser does not support geolocation.',
  geoDenied: 'Location access denied — enable it in your browser settings.',
  geoUnavailable: 'Could not determine your location.',
  geoTimeout: 'Locating took too long. Try again.',
  youAreHere: 'You are here',
  noFavorites: 'No favorites yet.',
  noFavoritesHint: 'Tap ★ next to a stop to keep it here.',
  noResults: 'Nothing found.',
  addFavorite: 'Add to favorites',
  removeFavorite: 'Remove from favorites',
  laterThanOfficial: 'min later than official',
  earlierThanOfficial: 'min earlier than official',
  matchesOfficial: 'matches official',
  officialShort: 'official',
  scheduleShort: 'timetable',
  modelNote: 'These times are our model’s prediction, learned from collected history — '
    + 'not TTC’s official estimate. The line underneath shows how far it differs from official.',
  modelNoteShort: 'model prediction, not official',
  refresh: 'Refresh',
  nearYou: 'Near you',
  away: 'away',
  m: 'm',
  km: 'km',
};

const STORAGE_KEY = 'tbsbus.lang';

@Injectable({ providedIn: 'root' })
export class I18nService {
  // signal — შაბლონები ავტომატურად გადაიხატება ენის შეცვლისას.
  readonly lang = signal<Lang>(this.initial());
  readonly t = signal<Strings>(this.lang() === 'en' ? EN : KA);

  private initial(): Lang {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'en' || saved === 'ka') { return saved; }
    } catch { /* private mode / storage disabled — ნაგულისხმევზე ვრჩებით */ }
    // ინგლისური არჩევითია: ნაგულისხმევად ყოველთვის ქართული ვრჩებით და ენა მხოლოდ მაშინ
    // იცვლება, როცა მომხმარებელი თავად გადართავს (არჩევანი localStorage-ში რჩება).
    return 'ka';
  }

  set(lang: Lang): void {
    this.lang.set(lang);
    this.t.set(lang === 'en' ? EN : KA);
    document.documentElement.lang = lang;
    try { localStorage.setItem(STORAGE_KEY, lang); } catch { /* არ არის კრიტიკული */ }
  }

  /** მანძილის ჩვენება — 950 მ, 1.2 კმ. */
  distance(meters: number): string {
    const t = this.t();
    return meters >= 1000 ? `${(meters / 1000).toFixed(1)} ${t.km}` : `${Math.round(meters)} ${t.m}`;
  }
}
