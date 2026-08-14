import type { ReactNode } from "react";

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return <header className="page-header"><div className="page-heading"><h2>{title}</h2>{description && <p>{description}</p>}</div>{actions && <div className="toolbar">{actions}</div>}</header>;
}
