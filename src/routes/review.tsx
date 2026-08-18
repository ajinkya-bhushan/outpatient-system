import { createFileRoute, Link } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";

import { Icon } from "@/components/clinical/Icon";
import { SideNav } from "@/components/clinical/SideNav";

export const Route = createFileRoute("/review")({
  head: () => ({
    meta: [
      { title: "Review & Edit Note | Clinical Documentation Assistant" },
      {
        name: "description",
        content:
          "Review the AI-drafted SOAP note section by section, trace statements back to the transcript and confirm suggested ICD-10 codes.",
      },
      { property: "og:title", content: "Review & Edit Note | Clinical Documentation Assistant" },
      {
        property: "og:description",
        content: "Edit the AI SOAP note, trace sources and confirm suggested ICD-10 codes.",
      },
    ],
  }),
  component: Review,
});

function SoapSection({
  icon,
  title,
  children,
}: {
  icon: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-surface-high bg-surface-lowest shadow-ambient">
      <div className="flex items-center justify-between border-b border-surface-high bg-surface-low px-6 py-4">
        <h2 className="flex items-center gap-2 font-headline text-headline-sm text-primary">
          <Icon name={icon} className="text-primary" />
          {title}
        </h2>
        <div className="flex gap-2">
          <button
            title="Regenerate"
            aria-label={`Regenerate ${title}`}
            className="rounded p-1.5 text-on-surface-variant transition-colors hover:bg-primary-container/20 hover:text-primary"
          >
            <Icon name="refresh" className="text-sm" />
          </button>
          <button className="rounded border border-outline-variant bg-surface px-3 py-1 text-body-sm text-primary transition-colors hover:bg-surface-high">
            Accept
          </button>
        </div>
      </div>
      {children}
    </section>
  );
}

function Review() {
  const [sourceOpen, setSourceOpen] = useState(false);

  return (
    <div className="flex h-screen flex-col overflow-hidden pb-24 md:flex-row md:pb-0">
      <header className="z-10 flex h-16 w-full shrink-0 items-center justify-between border-b border-outline-variant bg-surface px-4 py-1 md:hidden">
        <div className="flex items-center gap-2">
          <Link
            to="/analysis"
            aria-label="Go back"
            className="-ml-2 rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-high"
          >
            <Icon name="arrow_back" />
          </Link>
          <h1 className="font-headline text-headline-md font-bold text-on-surface">John Doe</h1>
        </div>
        <button
          aria-label="Actions"
          className="-mr-2 rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-high"
        >
          <Icon name="more_vert" />
        </button>
      </header>

      <SideNav activeLabel="Clinical History" />

      <main className="relative w-full flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1200px] p-4 pb-32 md:p-8">
          <div className="mb-8 hidden items-center justify-between md:flex">
            <div>
              <h1 className="mb-2 font-headline text-display-lg text-on-surface">
                Review &amp; Edit Note
              </h1>
              <p className="text-body-lg text-on-surface-variant">
                Patient: John Doe • DOB: 05/12/1980 • Encounter: May 15, 2024
              </p>
            </div>
            <button className="rounded-lg border border-outline px-4 py-2 text-body-md text-on-surface transition-colors hover:bg-surface-high">
              Save Draft
            </button>
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            <div className="space-y-6 lg:col-span-8">
              <SoapSection icon="person" title="Subjective">
                <div
                  contentEditable
                  suppressContentEditableWarning
                  className="p-6 text-body-md leading-relaxed text-on-surface outline-none focus-within:ring-2 focus-within:ring-primary focus-within:ring-inset"
                >
                  Patient presents today for follow-up of essential hypertension. He reports overall
                  feeling well, denying any chest pain, shortness of breath, or dizziness. He states
                  he has been trying to adhere to a low-sodium diet and has walked 30 minutes, 3
                  times a week. Home blood pressure readings over the last two weeks have ranged from
                  130-140 systolic over 80-90 diastolic.
                </div>
              </SoapSection>

              <SoapSection icon="monitor_heart" title="Objective">
                <div className="p-6 text-body-md leading-relaxed text-on-surface">
                  <div className="mb-4 flex flex-wrap gap-4 rounded-lg bg-surface-container p-4 font-data text-data-mono">
                    <span>
                      <span className="font-bold">BP:</span> 138/86 mmHg
                    </span>
                    <span>
                      <span className="font-bold">HR:</span> 72 bpm
                    </span>
                    <span>
                      <span className="font-bold">RR:</span> 16
                    </span>
                    <span>
                      <span className="font-bold">Temp:</span> 98.6 °F
                    </span>
                    <span>
                      <span className="font-bold">Wt:</span> 185 lbs
                    </span>
                  </div>
                  <div
                    contentEditable
                    suppressContentEditableWarning
                    className="-m-2 rounded p-2 outline-none focus-within:ring-2 focus-within:ring-primary focus-within:ring-inset"
                  >
                    General: Well-developed, well-nourished male in no acute distress.
                    <br />
                    CV: Regular rate and rhythm. Normal S1 and S2. No murmurs, rubs, or gallops.
                    <br />
                    Pulm: Clear to auscultation bilaterally. No wheezes, rales, or rhonchi.
                    <br />
                    Ext: No lower extremity edema. Peripheral pulses 2+ and equal bilaterally.
                  </div>
                </div>
              </SoapSection>

              <div className="relative">
                <SoapSection icon="fact_check" title="Assessment">
                  <div className="p-6 text-body-md leading-relaxed text-on-surface">
                    <p className="mb-2">1. Essential (primary) hypertension (I10)</p>
                    <p className="border-l-2 border-surface-highest pl-4 text-on-surface-variant">
                      Blood pressure is borderline controlled on current regimen of Lisinopril 20mg
                      daily. Patient shows fair adherence to lifestyle modifications.
                    </p>
                    <p className="mt-4 mb-2">2. Hyperlipidemia (E78.5)</p>
                    <p className="border-l-2 border-surface-highest pl-4 text-on-surface-variant">
                      Stable on Atorvastatin.{" "}
                      <button
                        onClick={() => setSourceOpen((v) => !v)}
                        className="confidence-low text-left"
                      >
                        Patient noted mild muscle aches in legs, possibly statin-related, though
                        recent CK levels were normal.
                      </button>
                    </p>
                  </div>
                </SoapSection>

                {sourceOpen ? (
                  <div className="absolute right-8 bottom-4 z-30 w-72 rounded-lg border border-outline-variant bg-surface-lowest p-4 shadow-lifted">
                    <div className="mb-2 flex items-start justify-between">
                      <h4 className="label-caps text-on-surface">Transcript Source</h4>
                      <button
                        aria-label="Close source"
                        onClick={() => setSourceOpen(false)}
                        className="text-outline hover:text-on-surface"
                      >
                        <Icon name="close" className="text-sm" />
                      </button>
                    </div>
                    <div className="rounded border-l-2 border-tertiary bg-surface-container p-2 text-body-sm text-on-surface-variant italic">
                      "Yeah doc, my legs have been a bit sore lately, especially my calves... but I'm
                      not sure if it's the new walking routine or those cholesterol pills."
                    </div>
                    <div className="mt-3 flex justify-end">
                      <button className="label-caps text-primary hover:underline">
                        Edit Assessment
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>

              <SoapSection icon="assignment" title="Plan">
                <div
                  contentEditable
                  suppressContentEditableWarning
                  className="p-6 text-body-md leading-relaxed text-on-surface outline-none focus-within:ring-2 focus-within:ring-primary focus-within:ring-inset"
                >
                  <ul className="list-disc space-y-2 pl-5">
                    <li>Continue Lisinopril 20mg PO daily.</li>
                    <li>
                      Emphasized the importance of continued dietary sodium restriction and regular
                      aerobic exercise.
                    </li>
                    <li>Advised patient to continue home blood pressure monitoring and keep a log.</li>
                    <li>
                      Re-check Basic Metabolic Panel (BMP) to monitor renal function and potassium
                      levels.
                    </li>
                    <li>
                      Regarding muscle aches, will hold Atorvastatin for 2 weeks to see if symptoms
                      resolve, then reconsider rechallenge or alternative agent.
                    </li>
                    <li>Follow-up appointment scheduled in 3 months.</li>
                  </ul>
                </div>
              </SoapSection>
            </div>

            <div className="space-y-6 lg:col-span-4">
              <div className="sticky top-6 rounded-xl border border-outline-variant bg-surface-bright p-6 shadow-ambient">
                <h3 className="mb-4 flex items-center gap-2 font-headline text-headline-sm text-on-surface">
                  <Icon name="medical_information" className="text-secondary" />
                  Suggested Codes
                </h3>
                <div className="space-y-4">
                  <div className="cursor-pointer rounded-lg border border-surface-highest bg-surface-lowest p-3 transition-colors hover:border-secondary">
                    <div className="flex items-start justify-between">
                      <span className="label-caps rounded bg-secondary-container px-2 py-1 text-on-secondary-container">
                        ICD-10
                      </span>
                      <Icon name="check_circle" className="text-sm text-secondary" />
                    </div>
                    <p className="mt-1 text-body-md font-bold">I10</p>
                    <p className="text-body-sm text-on-surface-variant">
                      Essential (primary) hypertension
                    </p>
                    <p className="label-caps mt-2 flex items-center gap-1 text-secondary">
                      <Icon name="info" className="text-[14px]" />
                      Match found in transcript
                    </p>
                  </div>
                  <div className="cursor-pointer rounded-lg border border-surface-highest bg-surface-lowest p-3 transition-colors hover:border-secondary">
                    <div className="flex items-start justify-between">
                      <span className="label-caps rounded bg-secondary-container px-2 py-1 text-on-secondary-container">
                        ICD-10
                      </span>
                    </div>
                    <p className="mt-1 text-body-md font-bold">E78.5</p>
                    <p className="text-body-sm text-on-surface-variant">
                      Hyperlipidemia, unspecified
                    </p>
                  </div>
                </div>
                <button className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-outline py-2 text-body-sm text-primary transition-colors hover:bg-primary-container/10">
                  <Icon name="add" className="text-sm" /> Add Code
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>

      <div className="fixed bottom-0 left-0 right-0 z-40 flex justify-end border-t border-outline-variant bg-surface/90 px-4 py-4 backdrop-blur-md md:left-80 md:px-8">
        <Link
          to="/sync"
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-8 py-3 font-headline text-headline-sm text-on-primary shadow-ambient transition-all hover:bg-primary-container hover:text-on-primary-container md:w-auto"
        >
          <Icon name="sync" />
          Approve &amp; Sync
        </Link>
      </div>
    </div>
  );
}
