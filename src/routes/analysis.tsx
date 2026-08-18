import { createFileRoute, Link } from "@tanstack/react-router";

import { Icon } from "@/components/clinical/Icon";

export const Route = createFileRoute("/analysis")({
  head: () => ({
    meta: [
      { title: "AI Analysis | Clinical Documentation Assistant" },
      {
        name: "description",
        content:
          "Live processing status while the encounter is transcribed, clinical entities are extracted and the SOAP note is generated.",
      },
      { property: "og:title", content: "AI Analysis | Clinical Documentation Assistant" },
      {
        property: "og:description",
        content: "Transcription, entity extraction and note generation progress for the encounter.",
      },
    ],
  }),
  component: Analysis,
});

function Analysis() {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden">
      <div className="pointer-events-none absolute inset-0 opacity-20">
        <div className="absolute top-1/4 left-1/4 h-96 w-96 animate-pulse rounded-full bg-primary-fixed blur-3xl" />
        <div
          className="absolute right-1/4 bottom-1/4 h-96 w-96 animate-pulse rounded-full bg-secondary-fixed blur-3xl"
          style={{ animationDelay: "2s" }}
        />
      </div>

      <main className="relative z-10 w-full max-w-lg px-4 md:px-8">
        <div className="flex flex-col items-center rounded-xl border border-outline-variant bg-surface-lowest p-6 text-center shadow-lifted">
          <div className="relative mb-6 flex h-24 w-24 items-center justify-center">
            <div className="pulse-ring absolute inset-0 rounded-full bg-primary-fixed opacity-20" />
            <div className="z-10 flex h-16 w-16 items-center justify-center rounded-full bg-primary-container text-on-primary-container shadow-ambient">
              <Icon name="memory" filled className="text-4xl" />
            </div>
          </div>

          <h1 className="mb-2 font-headline text-headline-md text-on-surface">
            Analyzing the encounter
          </h1>
          <p className="mb-8 text-body-md text-on-surface-variant">
            Estimated time: <span className="font-data font-bold text-primary">15 seconds</span>
          </p>

          <div className="w-full max-w-sm">
            <div className="relative mb-4 flex items-start">
              <div className="absolute top-6 bottom-[-16px] left-3 w-0.5 bg-primary" />
              <div className="z-10 mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary">
                <Icon name="check" className="text-sm font-bold text-on-primary" />
              </div>
              <div className="ml-4 flex flex-col text-left">
                <span className="text-body-sm text-on-surface">Transcribing</span>
              </div>
            </div>

            <div className="relative mb-4 flex items-start">
              <div className="absolute top-6 bottom-[-16px] left-3 w-0.5 bg-surface-high" />
              <div className="z-10 mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 border-primary bg-surface-lowest">
                <div className="h-2 w-2 animate-pulse rounded-full bg-primary" />
              </div>
              <div className="ml-4 flex flex-col text-left">
                <span className="text-body-sm font-bold text-primary">
                  Extracting clinical entities
                </span>
                <span className="label-caps mt-1 text-on-surface-variant">Processing context</span>
              </div>
            </div>

            <div className="flex items-start">
              <div className="z-10 mt-1 h-6 w-6 shrink-0 rounded-full border-2 border-surface-high bg-surface-lowest" />
              <div className="ml-4 flex flex-col text-left">
                <span className="text-body-sm text-on-surface-variant">Generating note</span>
              </div>
            </div>
          </div>

          <Link
            to="/review"
            className="mt-8 rounded-lg px-4 py-2 text-body-sm text-on-surface-variant transition-colors hover:bg-surface-low hover:text-on-surface"
          >
            Cancel Analysis
          </Link>
        </div>
      </main>
    </div>
  );
}
