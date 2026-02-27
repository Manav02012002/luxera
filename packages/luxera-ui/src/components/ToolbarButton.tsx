import type { ButtonHTMLAttributes, ReactNode } from "react";

type ToolbarButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
};

export function ToolbarButton({ children, className = "", ...rest }: ToolbarButtonProps) {
  return (
    <button
      type="button"
      className={`rounded-lg border border-border bg-panelSoft/70 px-3 py-2 text-sm text-text transition hover:border-accent/70 hover:text-accent ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
