import type { InputHTMLAttributes } from "react";

type TextFieldProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "id" | "name" | "autoComplete"
> & {
  label: string;
  name: string;
  autoComplete: string;
};

export function TextField({
  label,
  name,
  autoComplete,
  ...props
}: TextFieldProps) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <input
        className="field-input"
        name={name}
        autoComplete={autoComplete}
        {...props}
      />
    </label>
  );
}
