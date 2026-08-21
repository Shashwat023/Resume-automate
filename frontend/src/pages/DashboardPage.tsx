export const DashboardPage = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground mt-2 text-gray-500">
          Overview of your auto-apply progress and recent activity.
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {/* Placeholder cards */}
        <div className="rounded-xl border bg-card text-card-foreground shadow-sm p-6 bg-white dark:bg-gray-800 dark:border-gray-700">
          <div className="flex flex-row items-center justify-between space-y-0 pb-2">
            <h3 className="tracking-tight text-sm font-medium">Applications Sent</h3>
          </div>
          <div className="text-2xl font-bold">0</div>
        </div>
      </div>
    </div>
  );
};
