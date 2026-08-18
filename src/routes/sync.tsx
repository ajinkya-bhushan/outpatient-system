import { createFileRoute, Link } from "@tanstack/react-router";

import patientPortrait from "@/assets/patient-portrait.jpg";
import { Icon } from "@/components/clinical/Icon";

export const Route = createFileRoute("/sync")({
  head: () => ({
    meta: [
      { title: "Sync & Patient Instructions | Clinical Documentation Assistant" },
      {
        name: "description",
        content:
          "Confirmation that the encounter synced to the EHR, with plain-language patient instructions ready to share.",
      },
      {
        property: "og:title",
        content: "Sync & Patient Instructions | Clinical Documentation Assistant",
      },
      {
        property: "og:description",
        content: "EHR sync confirmation and plain-language patient instructions.",
      },
    ],
  }),
  component: Sync,
});

const resources = [
  {
    icon: "assignment",
    label: "Encounter",
    detail: "ID: 88291A",
    tone: "bg-secondary-container text-on-secondary-container",
  },
  {
    icon: "vital_signs",
    label: "Observation",
    detail: "Vitals Flowsheet",
    tone: "bg-primary-container text-on-primary-container",
  },
  {
    icon: "medical_information",
    label: "Condition",
    detail: "ICD-10 Added",
    tone: "bg-tertiary-container text-on-tertiary-container",
  },
];

const instructions = [
  { icon: "medication", text: "Continue Metformin." },
  { icon: "monitor_heart", text: "Check blood pressure daily." },
  { icon: "event", text: "Follow up in 3 months." },
];

function Sync() {
  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <header className="fixed top-0 z-50 flex w-full items-center justify-between border-b border-outline-variant bg-surface px-4 py-1 md:px-8">
        <div className="flex items-center gap-2">
          <img
            src={patientPortrait}
            alt="John Doe, patient photo"
            width={512}
            height={512}
            className="h-10 w-10 shrink-0 rounded-full border border-outline-variant object-cover"
          />
          <h1 className="font-headline text-headline-sm text-primary">John Doe</h1>
        </div>
        <button
          aria-label="Microphone"
          className="flex items-center justify-center rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-high"
        >
          <Icon name="mic" className="text-[24px]" />
        </button>
      </header>

      <main className="mx-auto mt-[64px] mb-[80px] flex w-full max-w-[1200px] flex-col gap-6 px-4 py-6 md:px-8 lg:grid lg:grid-cols-2 lg:items-start lg:gap-8">
        <section className="group relative flex flex-col gap-4 overflow-hidden rounded-xl border border-outline-variant bg-surface-lowest p-6 shadow-ambient">
          <div className="absolute -top-16 -right-16 h-48 w-48 rounded-full bg-primary-fixed/20 blur-3xl transition-colors duration-500 group-hover:bg-primary-fixed/30" />
          <header className="relative z-10 flex items-start justify-between gap-2">
            <div>
              <h2 className="mb-1 flex items-center gap-2 font-headline text-headline-sm text-on-surface">
                <Icon name="check_circle" filled className="text-secondary" />
                Syncing to Epic EHR...
              </h2>
              <p className="text-body-sm text-on-surface-variant">
                Data successfully transmitted and committed.
              </p>
            </div>
            <div className="label-caps flex shrink-0 items-center gap-1 rounded bg-surface-container px-2 py-1 text-on-surface-variant">
              <Icon name="cloud_sync" className="text-[16px]" />
              Live
            </div>
          </header>

          <div className="relative z-10 mt-2">
            <h3 className="label-caps mb-2 text-on-surface-variant">Updated Resources</h3>
            <div className="flex flex-wrap gap-2">
              {resources.map((r) => (
                <div
                  key={r.label}
                  className="flex min-w-[140px] flex-1 items-center gap-2 rounded-lg border border-outline-variant/50 bg-surface p-2"
                >
                  <div
                    className={`flex h-8 w-8 items-center justify-center rounded-md ${r.tone}`}
                  >
                    <Icon name={r.icon} className="text-[18px]" />
                  </div>
                  <div className="flex flex-col">
                    <span className="font-data text-data-mono text-on-surface">{r.label}</span>
                    <span className="label-caps text-outline">{r.detail}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="relative flex flex-col gap-4 overflow-hidden rounded-xl border border-primary-fixed-dim/30 bg-primary-fixed p-6 text-on-primary-fixed">
          <header className="relative z-10 flex items-center gap-2">
            <Icon name="prescriptions" className="text-[24px]" />
            <h2 className="font-headline text-headline-sm">Patient Instructions</h2>
          </header>
          <div className="relative z-10 flex flex-1 flex-col justify-center">
            <div className="rounded-lg border border-on-primary-fixed/10 bg-surface-lowest/50 p-4 backdrop-blur-sm">
              <ul className="flex flex-col gap-4">
                {instructions.map((item) => (
                  <li key={item.text} className="flex items-start gap-2">
                    <Icon name={item.icon} filled className="mt-[2px] text-[20px] text-primary" />
                    <span className="text-body-lg">{item.text}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="relative z-10 mt-auto pt-2">
            <p className="label-caps flex items-center gap-1 opacity-70">
              <Icon name="translate" className="text-[14px]" />
              Written in simple language (Reading level: 6th Grade)
            </p>
          </div>
        </section>
      </main>

      <footer className="fixed bottom-0 z-40 flex w-full items-center justify-end gap-4 border-t border-outline-variant bg-surface/90 px-4 py-2 backdrop-blur-md md:px-8">
        <button className="label-caps flex min-h-[44px] items-center gap-1 rounded-full border-2 border-primary px-6 py-2 text-primary transition-colors hover:bg-primary-fixed">
          <Icon name="ios_share" className="text-[18px]" />
          Share with Patient
        </button>
        <Link
          to="/"
          className="label-caps flex min-h-[44px] items-center gap-1 rounded-full bg-primary px-6 py-2 text-on-primary shadow-ambient transition-all hover:bg-surface-tint active:scale-95"
        >
          <Icon name="done_all" className="text-[18px]" />
          Close Encounter
        </Link>
      </footer>
    </div>
  );
}
