import { Link } from "@tanstack/react-router";

import { Icon } from "./Icon";

const items = [
  { icon: "medical_services", to: "/", label: "Encounter" },
  { icon: "history", to: "/record", label: "History" },
  { icon: "assignment", to: "/review", label: "Notes" },
  { icon: "settings", to: "/sync", label: "Settings" },
];

export function BottomNav({ activeTo = "/" }: { activeTo?: string }) {
  return (
    <nav className="fixed bottom-0 z-50 flex h-16 w-full items-center justify-around rounded-t-xl border-t border-outline-variant bg-surface-container px-4 md:hidden">
      {items.map((item) => {
        const active = item.to === activeTo;
        return (
          <Link
            key={item.label}
            to={item.to}
            aria-label={item.label}
            className={
              active
                ? "flex h-14 w-14 items-center justify-center rounded-full bg-primary-container p-3 text-on-primary-container transition-transform duration-150 active:scale-95"
                : "flex h-14 w-14 items-center justify-center rounded-full p-3 text-on-surface-variant transition-colors hover:bg-surface-variant"
            }
          >
            <Icon name={item.icon} filled={active} />
          </Link>
        );
      })}
    </nav>
  );
}
