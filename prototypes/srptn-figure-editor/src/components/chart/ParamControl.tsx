import type { DeriveControl } from "../../lib/chart/engine/transforms";

export function ParamControl({
  control,
  value,
  onChange,
  className,
}: {
  control: DeriveControl;
  value: unknown;
  onChange: (value: unknown) => void;
  className?: string;
}) {
  if (control.kind === "number") {
    return (
      <input
        className={className}
        type="number"
        min={control.min}
        placeholder={control.placeholder}
        value={typeof value === "number" ? value : ""}
        onChange={(event) =>
          onChange(
            event.target.value ? Number(event.target.value) : undefined,
          )
        }
      />
    );
  }
  if (control.kind === "select") {
    return (
      <select
        className={className}
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value)}
      >
        {control.options?.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }
  if (control.kind === "text") {
    return (
      <input
        className={className}
        value={typeof value === "string" ? value : ""}
        placeholder={control.placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }
  return null;
}
