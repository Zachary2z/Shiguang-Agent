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

const sharedRiskLabels: Readonly<Record<string, string>> = {
  "The item price needs confirmation.": "价格待确认。",
  "The plan budget cannot be verified until the price is confirmed.": "价格确认前无法核验预算。",
  "Weather conditions are not available for this plan.": "天气情况待确认。",
  "Weather information is temporarily unavailable.": "天气信息暂时不可用。",
  "The first route is unknown because no precise origin was provided.": "未提供精确起点，首段路线待确认。",
  "The opening hours need confirmation.": "营业时间待确认。",
};

export function sharedRiskLabel(risk: string) {
  return sharedRiskLabels[risk] ?? risk;
}
