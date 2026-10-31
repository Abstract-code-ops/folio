export default function Loading() {
  return (
    <div className="min-h-screen bg-bg-base">
      <div className="h-14 border-b border-border-subtle" />
      <main className="mx-auto max-w-5xl px-6 py-10">
        <div className="mb-8 h-8 w-40 animate-pulse rounded bg-bg-elevated" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <div
              key={index}
              className="flex flex-col overflow-hidden rounded-xl border border-border bg-bg-elevated"
            >
              <div className="aspect-[3/4] animate-pulse bg-bg-surface" />
              <div className="space-y-2 p-4">
                <div className="h-3.5 w-3/4 animate-pulse rounded bg-bg-surface" />
                <div className="h-3 w-1/2 animate-pulse rounded bg-bg-surface" />
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
