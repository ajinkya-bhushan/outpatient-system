import { Link } from "@tanstack/react-router";

import doctorPortrait from "@/assets/doctor-portrait.jpg";
import { Icon } from "./Icon";
import { cn } from "@/lib/utils";

type NavItem = {
  icon: string;
  label: string;
  to: string;
};

const items: NavItem[] = [
  { icon: "dashboard", label: "Patient Dashboard", to: "/" },
  { icon: "clinical_notes", label: "Clinical History", to: "/review" },
  { icon: "science", label: "Lab Results", to: "/analysis" },
  { icon: "settings", label: "Settings", to: "/sync" },
];

export function SideNav({ activeLabel }: { activeLabel: string }) {
  return (
    <nav className="hidden w-80 shrink-0 flex-col border-r border-outline-variant bg-surface pt-4 pb-4 md:flex">
      <div className="mb-6 px-4">
        <div className="flex items-center gap-4">
          <img
            src={doctorPortrait}
            alt="Dr. Smith, cardiology"
            width={512}
            height={512}
            loading="lazy"
            className="h-12 w-12 rounded-full border border-outline-variant object-cover"
          />
          <div>
            <h2 className="font-headline text-headline-sm text-primary">Dr. Smith</h2>
            <p className="text-body-sm text-on-surface-variant">Cardiology Dept.</p>
            <p className="label-caps mt-1 text-outline">MRN: 882-194</p>
          </div>
        </div>
      </div>
      <ul className="flex-1 space-y-1 px-2">
        {items.map((item) => {
          const active = item.label === activeLabel;
          return (
            <li key={item.label}>
              <Link
                to={item.to}
                className={cn(
                  "flex items-center gap-4 rounded-lg px-4 py-2 transition-colors",
                  active
                    ? "bg-secondary-container font-bold text-on-secondary-container"
                    : "text-on-surface-variant hover:bg-surface-high",
                )}
              >
                <Icon name={item.icon} filled={active} />
                <span className="label-caps">{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
