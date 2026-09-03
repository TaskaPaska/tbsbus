import { Injectable, signal } from '@angular/core';

// რჩეული გაჩერებები — მხოლოდ ბრაუზერში (localStorage). სერვერზე ანგარიშები არ გვაქვს და
// პირადი აპისთვის არც სჭირდება; ეს იმასაც ნიშნავს, რომ სია მოწყობილობებს შორის არ სინქრონდება.
const STORAGE_KEY = 'tbsbus.favorites';

@Injectable({ providedIn: 'root' })
export class FavoritesService {
  private readonly ids = signal<string[]>(this.load());
  readonly list = this.ids.asReadonly();

  private load(): string[] {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : [];
    } catch {
      return [];   // გაფუჭებული ჩანაწერი ან გამორთული storage — ცარიელი სია სჯობს ავარიას
    }
  }

  private persist(next: string[]): void {
    this.ids.set(next);
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch { /* არ არის კრიტიკული */ }
  }

  has(id: string): boolean {
    return this.ids().includes(id);
  }

  toggle(id: string): void {
    const cur = this.ids();
    this.persist(cur.includes(id) ? cur.filter(x => x !== id) : [...cur, id]);
  }
}
