// API-ს ტიპები (იხ. services/api/app.py და predict.py).

export interface Stop {
  id: string;
  name: string;
  lat: number;
  lon: number;
  // ცარიელია ქალაქის სრული სიის გაჩერებებისთვის (routes-density scan მხოლოდ tracked
  // ქვესიმრავლისთვის ხდება — იხ. list_all_stops.py vs. select_stops.py).
  routes?: string[];
}

export interface Arrival {
  route: string;
  headsign: string;
  pattern: string;
  operator_min: number;      // baseline: ოპერატორის realtimeArrivalMinutes
  scheduled_min: number | null;
  predicted_min: number;     // ჩვენი მოდელის კორექტირებული პროგნოზი
}

export interface PredictResponse {
  stop_id: string;
  arrivals: Arrival[];
}
