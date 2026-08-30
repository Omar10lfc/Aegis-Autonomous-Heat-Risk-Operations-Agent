"use client";

const STAGES = ["planner", "executor", "analyzer", "synthesizer"] as const;

export default function PipelineBar({
  stage,
  status,
}: {
  stage: string | null;
  status: string;
}) {
  const activeIdx = STAGES.indexOf((stage ?? "") as (typeof STAGES)[number]);
  return (
    <div className="pipeline" aria-label="pipeline stages">
      {STAGES.map((name, i) => {
        const cls =
          status === "succeeded" || (activeIdx > -1 && i < activeIdx)
            ? "stage done"
            : status === "running" && i === activeIdx
              ? "stage active"
              : "stage";
        return (
          <div key={name} className={cls}>
            {name}
          </div>
        );
      })}
    </div>
  );
}
