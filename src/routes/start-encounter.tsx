import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";

import { Icon } from "@/components/clinical/Icon";

export const Route = createFileRoute("/start-encounter")({
  head: () => ({
    meta: [
      { title: "Start Encounter | Clinical Documentation Assistant" },
      {
        name: "description",
        content:
          "Confirm patient recording consent, pick the encounter type and verify the microphone before ambient documentation begins.",
      },
      { property: "og:title", content: "Start Encounter | Clinical Documentation Assistant" },
      {
        property: "og:description",
        content: "Confirm consent, encounter type and microphone readiness before recording.",
      },
    ],
  }),
  component: StartEncounter,
});

const bars = Array.from({ length: 40 }, (_, i) => i);

function StartEncounter() {
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen items-center justify-center p-4 sm:p-6">
      <div className="flex w-full max-w-[600px] flex-col overflow-hidden rounded-xl border border-outline-variant bg-surface-lowest shadow-lifted">
        <div className="flex items-center justify-between border-b border-outline-variant bg-surface px-6 py-4">
          <h1 className="font-headline text-headline-sm text-on-surface">Start Encounter</h1>
          <Link
            to="/"
            aria-label="Close"
            className="rounded-full p-1 text-on-surface-variant transition-colors hover:bg-surface-high hover:text-on-surface"
          >
            <Icon name="close" />
          </Link>
        </div>

        <div className="flex flex-col gap-8 p-6">
          <div className="flex items-start gap-4 rounded-lg border border-primary-fixed-dim bg-primary-fixed p-4">
            <Icon name="info" className="text-on-primary-fixed" />
            <div>
              <h2 className="mb-1 font-headline text-headline-sm text-on-primary-fixed">
                Patient Consent
              </h2>
              <p className="text-body-md text-on-primary-fixed-variant">
                Has the patient consented to being recorded for this clinical encounter?
              </p>
            </div>
          </div>

          <div>
            <label
              htmlFor="encounter-type"
              className="label-caps mb-2 block text-on-surface-variant"
            >
              Encounter Type
            </label>
            <div className="relative">
              <select
                id="encounter-type"
                defaultValue="follow-up"
                className="w-full appearance-none rounded-lg border border-outline-variant bg-surface-low px-4 py-2 text-body-md text-on-surface focus:border-transparent focus:ring-2 focus:ring-primary focus:outline-none"
              >
                <option value="follow-up">Follow-up Visit</option>
                <option value="new-patient">New Patient Visit</option>
                <option value="consultation">Consultation</option>
                <option value="procedure">Procedure</option>
              </select>
              <Icon
                name="expand_more"
                className="pointer-events-none absolute top-1/2 right-md -translate-y-1/2 text-on-surface-variant"
              />
            </div>
          </div>

          <div className="rounded-lg border border-outline-variant bg-surface-container p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="label-caps text-on-surface-variant">Microphone Check</span>
              <span className="flex items-center gap-1 text-body-sm text-secondary">
                <Icon name="check_circle" className="text-[16px]" /> Ready
              </span>
            </div>
            <div className="mx-auto flex h-16 w-full max-w-[200px] items-center justify-center gap-[2px] overflow-hidden">
              {bars.map((i) => (
                <div
                  key={i}
                  className="waveform-bar h-full w-1 rounded-full bg-secondary"
                  style={{ animationDelay: `${(i % 7) * -0.28}s` }}
                />
              ))}
            </div>
          </div>
        </div>

        <div className="mt-auto flex justify-end gap-4 border-t border-outline-variant bg-surface px-6 py-4">
          <Link
            to="/"
            className="rounded-lg px-4 py-2 text-body-md font-semibold text-on-surface-variant transition-colors hover:bg-surface-high hover:text-on-surface"
          >
            Cancel
          </Link>
          <button
            onClick={() => navigate({ to: "/record" })}
            className="flex items-center gap-1 rounded-lg bg-primary px-6 py-2 text-body-md font-semibold text-on-primary transition-colors hover:bg-primary-container hover:text-on-primary-container"
          >
            <Icon name="mic" />
            Begin Recording
          </button>
        </div>
      </div>
    </div>
  );
}
