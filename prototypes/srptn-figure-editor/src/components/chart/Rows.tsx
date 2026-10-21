import type { ReactNode } from "react";

export function Row({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={className ? `row ${className}` : "row"}>{children}</div>
  );
}

export function RowList({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={className ? `row-list ${className}` : "row-list"}>
      {children}
    </div>
  );
}
