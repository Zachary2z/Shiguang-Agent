type EmptyRouteProps = {
  eyebrow: string;
  title: string;
  description: string;
};

export function EmptyRoute({
  eyebrow,
  title,
  description,
}: EmptyRouteProps) {
  return (
    <>
      <header className="page-intro">
        <p className="page-eyebrow">{eyebrow}</p>
        <h1 className="page-title">{title}</h1>
        <p className="page-description">{description}</p>
      </header>
      <section className="foundation-card" aria-labelledby="foundation-title">
        <h2 id="foundation-title">这里还很安静</h2>
        <p>
          页面结构、导航和共同状态已经准备好。具体内容会在对应业务阶段接入，不使用模拟数据提前填充。
        </p>
        <span className="foundation-note">M1-2 · 基础路由</span>
      </section>
    </>
  );
}
