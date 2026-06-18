// API-ს ტიპები (იხ. services/api/app.py და predict.py).

export interface Stop {
  id: string;
  name: string;
  lat: number;
  lon: number;
  routes: string[];
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
