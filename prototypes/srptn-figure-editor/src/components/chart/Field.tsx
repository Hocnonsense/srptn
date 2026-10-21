import type { ReactNode } from "react";

export function Field({
  label,
  error,
  className,
  children,
}: {
  label?: ReactNode;
  error?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label className={className ? `field ${className}` : "field"}>
      {label !== undefined ? (
        <span className="field-label">{label}</span>
      ) : null}
      {children}
      {error ? <span className="field-error">{error}</span> : null}
    </label>
  );
}
