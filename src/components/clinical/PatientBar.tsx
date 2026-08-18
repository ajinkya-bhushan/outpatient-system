import patientPortrait from "@/assets/patient-portrait.jpg";
import { Icon } from "./Icon";
import type { ReactNode } from "react";

type PatientBarProps = {
  name: string;
  meta?: string;
  showMenu?: boolean;
  center?: ReactNode;
  titleClassName?: string;
};

export function PatientBar({
  name,
  meta,
  showMenu = false,
  center,
  titleClassName = "font-headline text-headline-md font-bold text-on-surface",
}: PatientBarProps) {
  return (
    <header className="sticky top-0 z-40 flex w-full items-center justify-between gap-4 border-b border-outline-variant bg-surface px-4 py-1 md:px-8">
      <div className="flex items-center gap-4">
        {showMenu ? (
          <button
            aria-label="Open menu"
            className="flex items-center justify-center rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-high md:hidden"
          >
            <Icon name="menu" />
          </button>
        ) : null}
        <div className="flex items-center gap-2">
          <img
            src={patientPortrait}
            alt={`${name}, patient photo`}
            width={512}
            height={512}
            className="h-10 w-10 rounded-full border border-outline-variant object-cover"
          />
          <div>
            <h1 className={titleClassName}>{name}</h1>
            {meta ? <p className="label-caps text-on-surface-variant">{meta}</p> : null}
          </div>
        </div>
      </div>
      {center}
      <button
        aria-label="Microphone"
        className="flex items-center justify-center rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-high"
      >
        <Icon name="mic" />
      </button>
    </header>
  );
}
