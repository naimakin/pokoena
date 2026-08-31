export function ComingSoon({ label, description }: { label: string; description: string }) {
  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          <b>{label}</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">{label}</div>
            <div className="page-desc">{description}</div>
          </div>
        </div>
        <div className="card">
          <p className="empty-state">Coming soon.</p>
        </div>
      </div>
    </>
  );
}
