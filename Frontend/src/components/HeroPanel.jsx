export default function HeroPanel({ summary }) {
  return (
    <section className="panel-shell p-6 sm:p-8">
      <h2 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
        Workload Shift Plan
      </h2>

      <p className="mt-4 max-w-3xl text-sm leading-relaxed text-muted sm:text-base">
        {summary}
      </p>
    </section>
  );
}
