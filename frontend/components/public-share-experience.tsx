"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { API_BASE_URL } from "@/lib/api-client";
import { sharedRiskLabel, type PublicPlanShare, type SharedPlanSnapshot } from "@/lib/share-contracts";

const transportLabels: Record<string, string> = {
  walking: "步行",
  cycling: "骑行",
  transit: "公共交通",
  driving: "驾车",
};

function clock(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function date(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
  }).format(new Date(value));
}

function dateTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function minutes(seconds: number) {
  return `${Math.round(seconds / 60)} 分钟`;
}

function ShareUnavailable({ cancelled = false }: { cancelled?: boolean }) {
  return (
    <main className="public-share-state">
      <span className="share-mark" aria-hidden="true">拾</span>
      <p className="eyebrow">Read-only journey</p>
      <h1>{cancelled ? "行程已取消" : "这份行程暂时无法查看"}</h1>
      <p>
        {cancelled
          ? "计划者已取消这次行程，页面不再展示原有安排。"
          : "链接可能已撤销、已过期或不正确。为保护隐私，我们不会说明具体原因。"}
      </p>
      <Link className="primary-button" href="/agent">生成我的计划</Link>
    </main>
  );
}

function ActiveShare({ plan }: { plan: SharedPlanSnapshot }) {
  const firstMap = plan.items.find((item) => item.map_url)?.map_url;
  return (
    <main className="public-share">
      <header className="public-share-hero">
        <div className="public-share-brand">
          <span className="share-mark" aria-hidden="true">拾</span>
          <span>拾光 · 只读行程</span>
        </div>
        <span className="readonly-badge">READ ONLY</span>
        <p>{date(plan.start_at)}</p>
        <h1>{plan.items.map((item) => item.title).join(" → ")}</h1>
        <dl>
          <div><dt>出发范围</dt><dd>{plan.origin_label}</dd></div>
          <div><dt>确认版本</dt><dd>V{plan.version}</dd></div>
          <div><dt>更新时间</dt><dd>{dateTime(plan.updated_at)}</dd></div>
        </dl>
      </header>

      <section className="public-share-route" aria-labelledby="public-route-title">
        <div className="public-share-section-title">
          <p className="eyebrow">Latest confirmed route</p>
          <h2 id="public-route-title">当天安排</h2>
        </div>
        <ol className="public-time-rail">
          {plan.items.map((item, index) => (
            <li key={`${item.title}-${item.start_at}`}>
              <time>{clock(item.start_at)}</time>
              <span className="public-node" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
              <article>
                <div className="public-item-heading">
                  <h3>{item.title}</h3>
                  <span>{item.source_label}</span>
                </div>
                <p>{clock(item.start_at)}—{clock(item.end_at)} · 停留 {minutes(item.visit_duration_seconds)}</p>
                {item.public_address && <address>{item.public_address}</address>}
                <p>
                  {item.travel_duration_seconds === null
                    ? "首段路线待确认（未提供精确起点）"
                    : `抵达：${transportLabels[item.transport_mode] ?? item.transport_mode} · ${minutes(item.travel_duration_seconds)}${item.travel_distance_meters && item.travel_distance_meters > 0 ? ` · ${(item.travel_distance_meters / 1000).toFixed(1)} km` : ""}`}
                </p>
                {item.buffer_after_seconds > 0 && <p>预留缓冲 {minutes(item.buffer_after_seconds)}</p>}
                <p>费用：{item.price_amount === null ? "待确认" : `¥${item.price_amount}`}</p>
                {item.queried_at && <p className="public-query-time">地点信息查询于 {dateTime(item.queried_at)}</p>}
                {item.risks.length > 0 && <ul>{item.risks.map((risk) => <li key={risk}>{sharedRiskLabel(risk)}</li>)}</ul>}
                {item.map_url && <a href={item.map_url} target="_blank" rel="noreferrer">打开公开地点 / 路线</a>}
              </article>
            </li>
          ))}
        </ol>
        {plan.weather_status && (
          <aside className="public-risks">
            <strong>天气事实</strong>
            <p>
              {plan.weather_summary ?? plan.weather_status}
              {plan.weather_source ? ` · ${plan.weather_source}` : ""}
              {plan.weather_queried_at ? ` · ${dateTime(plan.weather_queried_at)}` : ""}
            </p>
          </aside>
        )}
        {plan.risks.length > 0 && <aside className="public-risks"><strong>出发前留意</strong><p>{plan.risks.map(sharedRiskLabel).join("；")}</p></aside>}
      </section>

      <footer className="public-share-footer">
        <p>链接将在 {dateTime(plan.expires_at)} 自动失效</p>
        <div>
          {firstMap && <a className="primary-button" href={firstMap} target="_blank" rel="noreferrer">查看路线</a>}
          <Link href="/agent">生成我的计划</Link>
        </div>
      </footer>
    </main>
  );
}

export function PublicShareExperience({ token }: { token?: string }) {
  const [result, setResult] = useState<PublicPlanShare | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      const bearer = token ?? window.location.hash.slice(1);
      if (!bearer) {
        setResult({ status: "unavailable", plan: null });
        return;
      }
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/v1/public/plan-share`,
          {
            cache: "no-store",
            credentials: "omit",
            headers: { Authorization: `Share ${bearer}` },
            referrerPolicy: "no-referrer",
            signal: controller.signal,
          },
        );
        if (!response.ok) throw new Error("public share unavailable");
        setResult((await response.json()) as PublicPlanShare);
      } catch {
        if (!controller.signal.aborted) {
          setResult({ status: "unavailable", plan: null });
        }
      }
    }
    void load();
    return () => controller.abort();
  }, [token]);

  if (!result) {
    return <main className="public-share-state" aria-busy="true"><span className="share-loader" aria-hidden="true" /><p role="status">正在读取只读行程…</p></main>;
  }
  if (result.status === "cancelled") return <ShareUnavailable cancelled />;
  if (result.status !== "active" || !result.plan) return <ShareUnavailable />;
  return <ActiveShare plan={result.plan} />;
}
