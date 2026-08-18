import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import patientPortrait from "@/assets/patient-portrait.jpg";
import { Icon } from "@/components/clinical/Icon";

export const Route = createFileRoute("/record")({
  head: () => ({
    meta: [
      { title: "Record & Transcribe | Clinical Documentation Assistant" },
      {
        name: "description",
        content:
          "Live ambient transcript of the visit with speaker turns, low-confidence flags and real-time AI clinical insights.",
      },
      { property: "og:title", content: "Record & Transcribe | Clinical Documentation Assistant" },
      {
        property: "og:description",
        content: "Live transcript with speaker turns, confidence flags and AI clinical insights.",
      },
    ],
  }),
  component: Record,
});

const turns = [
  {
    speaker: "Dr. Smith",
    initials: "DS",
    time: "10:02 AM",
    text: "Good morning, John. How have you been feeling since our last adjustment to your blood pressure medication?",
    self: false,
  },
  {
    speaker: "John Doe",
    initials: "JD",
    time: "10:02 AM",
    text: "Honestly, doc, I've been really tired lately. Like, an unusual amount of fatigue. And I've had this persistent headache for the last three days.",
    self: true,
  },
  {
    speaker: "Dr. Smith",
    initials: "DS",
    time: "10:03 AM",
    text: "I see. A persistent headache and unusual fatigue. Have you noticed any dizziness when standing up, or any changes in your vision?",
    self: false,
  },
];

function Record() {
  const [seconds, setSeconds] = useState(252);

  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const timer = `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <header className="z-10 flex w-full shrink-0 items-center justify-between gap-4 border-b border-outline-variant bg-surface px-4 py-1 md:px-8">
        <div className="flex items-center gap-4">
          <img
            src={patientPortrait}
            alt="John Doe, patient photo"
            width={512}
            height={512}
            className="h-10 w-10 rounded-full border border-outline-variant object-cover"
          />
          <div>
            <h1 className="font-headline text-headline-sm text-primary">John Doe</h1>
            <p className="label-caps text-on-surface-variant">DOB: 05/12/1980 • MRN: 48291A</p>
          </div>
        </div>

        <div className="flex items-center gap-2 rounded-full border border-error-container bg-error-container/30 px-4 py-2">
          <div className="rec-pulse h-3 w-3 rounded-full bg-error" />
          <span className="font-data text-data-mono font-bold tracking-widest text-error">
            {timer}
          </span>
          <span className="label-caps ml-2 hidden text-on-surface-variant sm:inline">Recording</span>
        </div>

        <button
          aria-label="Microphone"
          className="flex items-center justify-center rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-high"
        >
          <Icon name="mic" />
        </button>
      </header>

      <main className="relative flex flex-1 flex-col overflow-hidden md:flex-row">
        <section className="flex h-full flex-1 flex-col bg-surface-lowest">
          <div className="z-10 flex items-center justify-between border-b border-surface-variant bg-surface-bright p-4">
            <h2 className="text-body-md font-bold text-on-surface">Live Transcript</h2>
            <div className="flex items-center gap-2">
              <Icon name="hearing" className="text-sm text-outline" />
              <span className="text-body-sm text-outline">Listening...</span>
            </div>
          </div>

          <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-6 pb-32">
            {turns.map((turn) => (
              <div
                key={turn.speaker + turn.time + turn.text.slice(0, 8)}
                className={
                  turn.self
                    ? "flex max-w-3xl flex-row-reverse gap-4 self-end"
                    : "flex max-w-3xl gap-4"
                }
              >
                <div
                  className={
                    turn.self
                      ? "flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary-container text-on-secondary-container"
                      : "flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-container text-on-primary-container"
                  }
                >
                  <span className="label-caps">{turn.initials}</span>
                </div>
                <div className={turn.self ? "flex flex-col items-end gap-1" : "flex flex-col gap-1"}>
                  <span className="label-caps text-on-surface-variant">
                    {turn.speaker} • {turn.time}
                  </span>
                  <p
                    className={
                      turn.self
                        ? "rounded-lg rounded-tr-none border border-outline-variant bg-surface-bright p-4 text-body-md text-on-surface"
                        : "rounded-lg rounded-tl-none border border-surface-variant bg-surface-low p-4 text-body-md text-on-surface"
                    }
                  >
                    {turn.text}
                  </p>
                </div>
              </div>
            ))}

            <div className="flex max-w-3xl flex-row-reverse gap-4 self-end">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary-container text-on-secondary-container">
                <span className="label-caps">JD</span>
              </div>
              <div className="flex flex-col items-end gap-1">
                <span className="label-caps text-on-surface-variant">John Doe • 10:04 AM</span>
                <p className="rounded-lg rounded-tr-none border border-outline-variant bg-surface-bright p-4 text-body-md text-on-surface">
                  No dizziness really, but maybe a little bit of light sensitivity with the headache.
                  It's mostly just right here behind my eyes.
                </p>
                <div className="group relative mt-2 inline-flex w-full items-center gap-1 rounded border border-error-container bg-error-container/20 p-2 text-body-sm text-on-surface">
                  <Icon name="warning" className="text-[16px] text-error" />
                  <span className="confidence-low pb-0.5">...light sensitivity...</span>
                  <div className="absolute bottom-full left-0 z-20 mb-2 hidden w-64 rounded border border-outline bg-surface-highest p-2 shadow-lifted group-hover:block">
                    <p className="label-caps mb-1 text-on-surface-variant">AI Confidence: Low</p>
                    <p className="text-body-sm text-on-surface">
                      Audio unclear. Verify 'light sensitivity' or 'slight sensitivity'.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-2 flex max-w-3xl items-center gap-4 opacity-60">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-variant">
                <Icon name="more_horiz" className="text-[16px] text-outline" />
              </div>
              <div className="inline-flex items-center gap-1 rounded-lg rounded-tl-none bg-surface-container p-2">
                {[0, 150, 300].map((delay) => (
                  <div
                    key={delay}
                    className="h-1.5 w-1.5 animate-bounce rounded-full bg-outline"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                ))}
              </div>
            </div>
          </div>
        </section>

        <aside className="z-20 flex h-64 w-full shrink-0 flex-col border-t border-outline-variant bg-surface shadow-lifted md:h-full md:w-80 md:border-t-0 md:border-l md:shadow-none">
          <div className="flex items-center justify-between border-b border-outline-variant bg-surface-low p-4">
            <h3 className="flex items-center gap-2 text-body-md font-bold text-on-surface">
              <Icon name="psychiatry" className="text-[20px] text-primary" />
              Live Insights
            </h3>
            <span className="label-caps rounded-full border border-primary/20 bg-primary/10 px-2 py-1 text-primary">
              AI Active
            </span>
          </div>

          <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-4">
            <div>
              <h4 className="label-caps mb-2 text-on-surface-variant">Detected Symptoms</h4>
              <div className="flex flex-wrap gap-2">
                <div className="flex items-center gap-2 rounded-lg border border-tertiary-container/30 bg-tertiary-container/10 px-3 py-1.5">
                  <Icon name="sick" className="text-[16px] text-tertiary" />
                  <span className="text-body-sm font-medium text-tertiary">Fatigue</span>
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-tertiary-container/30 bg-tertiary-container/10 px-3 py-1.5">
                  <Icon name="sentiment_dissatisfied" className="text-[16px] text-tertiary" />
                  <span className="text-body-sm font-medium text-tertiary">Headache</span>
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-outline-variant bg-surface-highest px-3 py-1.5">
                  <Icon name="light_mode" className="text-[16px] text-on-surface-variant" />
                  <span className="text-body-sm font-medium text-on-surface-variant">
                    Photophobia?
                  </span>
                </div>
              </div>
            </div>

            <div>
              <h4 className="label-caps mb-2 text-on-surface-variant">Suggested Actions</h4>
              <ul className="flex flex-col gap-2">
                <li className="flex cursor-pointer items-start gap-2 rounded border border-outline-variant bg-surface-bright p-2 transition-colors hover:bg-surface-low">
                  <Icon name="neurology" className="mt-0.5 text-[18px] text-primary" />
                  <span className="text-body-sm text-on-surface">Order Neurological Exam</span>
                </li>
                <li className="flex cursor-pointer items-start gap-2 rounded border border-outline-variant bg-surface-bright p-2 transition-colors hover:bg-surface-low">
                  <Icon name="bloodtype" className="mt-0.5 text-[18px] text-primary" />
                  <span className="text-body-sm text-on-surface">Check CBC & Metabolic Panel</span>
                </li>
              </ul>
            </div>

            <div className="mt-auto border-t border-outline-variant pt-4">
              <button className="flex w-full items-center justify-center gap-2 rounded-lg border border-outline-variant bg-surface-highest py-2 text-on-surface transition-colors hover:bg-surface-variant focus:ring-2 focus:ring-primary focus:outline-none">
                <Icon name="flag" filled className="text-[20px]" />
                <span className="text-body-md font-medium">Flag Important</span>
              </button>
              <p className="label-caps mt-2 text-center text-outline">
                Manually mark current discussion
              </p>
            </div>
          </div>
        </aside>

        <div className="pointer-events-none absolute bottom-0 left-0 right-0 z-30 flex justify-center bg-gradient-to-t from-surface to-transparent p-4 pb-6 md:right-80">
          <div className="pointer-events-auto flex items-center gap-2 rounded-full border border-outline-variant bg-surface-highest p-2 shadow-lifted">
            <button className="group flex items-center gap-2 rounded-full border border-outline-variant bg-surface px-6 py-3 text-on-surface transition-colors hover:bg-surface-container">
              <Icon
                name="pause_circle"
                className="text-secondary transition-transform group-hover:scale-110"
              />
              <span className="text-body-md font-bold">Pause</span>
            </button>
            <div className="mx-2 h-8 w-px bg-outline-variant" />
            <Link
              to="/analysis"
              className="group flex items-center gap-2 rounded-full bg-error px-6 py-3 text-on-error shadow-ambient transition-colors hover:bg-tertiary"
            >
              <Icon name="stop_circle" className="transition-transform group-hover:scale-110" />
              <span className="text-body-md font-bold">End Encounter</span>
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
