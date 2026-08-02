export type OwnerShareStatus = "inactive" | "active" | "expired";

export type OwnerPlanShare = {
  status: OwnerShareStatus;
  created_at: string | null;
  expires_at: string | null;
  share_url: string | null;
  created: boolean;
};

export type SharedPlanItem = {
  title: string;
  start_at: string;
  end_at: string;
  public_address: string | null;
  visit_duration_seconds: number;
  transport_mode: string;
  travel_duration_seconds: number | null;
  travel_distance_meters: number | null;
  buffer_after_seconds: number;
  price_amount: string | null;
  price_currency: string | null;
  source_label: string;
  risks: string[];
  queried_at: string | null;
  map_url: string | null;
};

export type SharedPlanSnapshot = {
  version: number;
  confirmed_at: string;
  updated_at: string;
  start_at: string;
  end_at: string;
  origin_label: string;
  items: SharedPlanItem[];
  total_cost_amount: string | null;
  total_cost_currency: string | null;
  risks: string[];
  weather_status?: string | null;
  weather_source?: string | null;
  weather_queried_at?: string | null;
  weather_summary?: string | null;
  expires_at: string;
};

export type PublicPlanShare = {
  status: "active" | "cancelled" | "unavailable";
  plan: SharedPlanSnapshot | null;
};
