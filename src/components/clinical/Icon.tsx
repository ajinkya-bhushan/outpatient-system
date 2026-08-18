import { cn } from "@/lib/utils";

type IconProps = {
  name: string;
  filled?: boolean;
  className?: string;
};

export function Icon({ name, filled = false, className }: IconProps) {
  return (
    <span
      aria-hidden="true"
      className={cn("material-symbols-outlined select-none", filled && "icon-filled", className)}
    >
      {name}
    </span>
  );
}
