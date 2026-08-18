import { createFileRoute, Link } from "@tanstack/react-router";

import { BottomNav } from "@/components/clinical/BottomNav";
import { Icon } from "@/components/clinical/Icon";
import { PatientBar } from "@/components/clinical/PatientBar";
import { SideNav } from "@/components/clinical/SideNav";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Pre-Visit Dashboard | Clinical Documentation Assistant" },
      {
        name: "description",
        content:
          "Pre-visit patient snapshot: critical allergies, chief complaint, recent labs and active medications before starting the encounter.",
      },
      { property: "og:title", content: "Pre-Visit Dashboard | Clinical Documentation Assistant" },
      {
        property: "og:description",
        content:
          "Pre-visit patient snapshot: critical allergies, chief complaint, recent labs and active medications.",
      },
    ],
  }),
  component: Dashboard,
});

const medications = [
  { name: "Lisinopril", detail: "20mg • PO • Daily" },
  { name: "Metformin", detail: "500mg • PO • BID" },
  { name: "Atorvastatin", detail: "40mg • PO • Nightly" },
];

function Dashboard() {
  return (
    <div className="flex min-h-screen flex-col pb-24 md:flex-row md:pb-0">
      <SideNav activeLabel="Patient Dashboard" />
      <div className="flex min-w-0 flex-1 flex-col">
        <PatientBar name="John Doe" meta="68y • MRN: 882-194" showMenu />
        <main className="mx-auto flex w-full max-w-[1200px] flex-1 flex-col gap-6 px-4 py-6 md:px-8">
          <section className="relative overflow-hidden rounded-xl border border-error bg-error-container p-4 shadow-ambient">
            <div className="absolute top-0 right-0 p-2 opacity-20">
              <Icon name="warning" filled className="text-[64px] text-error" />
            </div>
            <div className="relative z-10 flex items-start gap-2">
              <Icon name="warning" filled className="mt-1 text-on-error-container" />
              <div>
                <h2 className="label-caps mb-1 text-on-error-container">Critical Allergies</h2>
                <p className="font-headline text-headline-sm font-bold text-on-error-container">
                  Penicillin
                </p>
                <p className="mt-1 text-body-sm font-medium text-on-error-container">
                  Reaction: Anaphylaxis
                </p>
              </div>
            </div>
          </section>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            <section className="flex flex-col rounded-xl border border-outline-variant bg-surface-lowest p-6 shadow-ambient md:col-span-2 lg:col-span-3">
              <h2 className="label-caps mb-2 flex items-center gap-1 text-on-surface-variant">
                <Icon name="chat_bubble" className="text-[16px]" />
                Chief Complaint
              </h2>
              <blockquote className="border-l-4 border-primary pl-4 font-headline text-headline-md text-on-surface italic">
                "Follow-up for blood pressure management and recent fatigue."
              </blockquote>
            </section>

            <section className="group relative flex cursor-pointer flex-col overflow-hidden rounded-xl border border-outline-variant bg-surface-lowest p-2 shadow-ambient transition-colors hover:border-tertiary-container">
              <div className="flex items-center justify-between border-b border-surface-variant px-2 pt-2 pb-1">
                <h2 className="label-caps flex items-center gap-1 text-on-surface-variant">
                  <Icon name="science" className="text-[16px]" />
                  Recent Labs
                </h2>
                <Icon
                  name="open_in_new"
                  className="text-[20px] text-on-surface-variant group-hover:text-tertiary"
                />
              </div>
              <div className="flex flex-col gap-2 p-2">
                <div className="flex items-end justify-between rounded-lg border border-error/20 bg-error-container/30 p-2">
                  <div>
                    <p className="text-body-sm text-on-surface-variant">Hemoglobin A1c</p>
                    <p className="flex items-center gap-1 font-headline text-headline-sm font-bold text-tertiary">
                      7.2%
                      <Icon name="arrow_upward" filled className="text-[18px]" />
                    </p>
                  </div>
                  <span className="label-caps rounded bg-error-container px-2 py-1 text-on-error-container">
                    Abnormal
                  </span>
                </div>
                <div className="flex items-end justify-between rounded-lg border border-outline-variant bg-surface p-2">
                  <div>
                    <p className="text-body-sm text-on-surface-variant">Blood Pressure (Recent)</p>
                    <p className="flex items-center gap-1 font-headline text-headline-sm font-bold text-on-surface">
                      142/90
                      <Icon name="warning" filled className="text-[18px] text-tertiary" />
                    </p>
                  </div>
                  <span className="font-data text-data-mono text-on-surface-variant">mmHg</span>
                </div>
              </div>
            </section>

            <section className="flex flex-col rounded-xl border border-outline-variant bg-surface-lowest p-2 shadow-ambient">
              <div className="flex items-center justify-between border-b border-surface-variant px-2 pt-2 pb-1">
                <h2 className="label-caps flex items-center gap-1 text-on-surface-variant">
                  <Icon name="medication" className="text-[16px]" />
                  Active Medications
                </h2>
              </div>
              <div className="flex flex-col gap-1 p-2">
                {medications.map((med) => (
                  <div
                    key={med.name}
                    className="flex items-center gap-2 rounded-lg p-2 transition-colors hover:bg-surface-low"
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded bg-primary-container/20 text-primary">
                      <Icon name="pill" className="text-[20px]" />
                    </div>
                    <div className="flex-1">
                      <p className="text-body-md font-bold text-on-surface">{med.name}</p>
                      <p className="font-data text-label-caps text-on-surface-variant">
                        {med.detail}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="flex flex-col rounded-xl border border-outline-variant bg-surface-lowest p-2 shadow-ambient">
              <div className="flex items-center justify-between border-b border-surface-variant px-2 pt-2 pb-1">
                <h2 className="label-caps flex items-center gap-1 text-on-surface-variant">
                  <Icon name="fact_check" className="text-[16px]" />
                  Active Problems
                </h2>
              </div>
              <div className="flex flex-wrap gap-1 p-2">
                {["Chronic Hypertension", "Type 2 Diabetes"].map((problem) => (
                  <span
                    key={problem}
                    className="inline-flex items-center rounded-full border border-outline-variant bg-surface-high px-3 py-1 text-body-sm text-on-surface"
                  >
                    {problem}
                  </span>
                ))}
              </div>
            </section>
          </div>
        </main>

        <div className="fixed bottom-16 left-0 z-40 flex w-full justify-center border-t border-outline-variant bg-surface/90 p-4 backdrop-blur-md md:bottom-0 md:pl-80">
          <Link
            to="/start-encounter"
            className="flex w-full max-w-md items-center justify-center gap-2 rounded-full bg-primary py-4 font-headline text-headline-sm font-bold text-on-primary shadow-ambient transition-all hover:bg-primary-container active:scale-95"
          >
            <Icon name="play_arrow" filled />
            Start Encounter
          </Link>
        </div>
      </div>
      <BottomNav activeTo="/" />
    </div>
  );
}
