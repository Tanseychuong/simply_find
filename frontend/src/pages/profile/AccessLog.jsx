import { Eye } from "lucide-react";
import { profileApi } from "../../api/profile";
import { errorMessage } from "../../api/client";
import { Alert, Card, EmptyState, Spinner } from "../../components/ui";
import { useApi, useTitle } from "../../lib/hooks";

function when(value) {
  return new Date(value).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function AccessLog() {
  useTitle("Who opened my files");
  const { data, loading, error } = useApi((signal) => profileApi.accessLog({ signal }), []);

  return (
    <Card className="p-4 sm:p-6">
      <h2 className="text-xl font-semibold">Who opened my files</h2>
      <p className="mt-1 text-sm text-muted">
        Every time someone on a hiring team opens a document from one of your applications, it's recorded here. Only teams you applied
        to can open them.
      </p>
      <div className="mt-6">
        {loading && !data ? (
          <Spinner />
        ) : error ? (
          <Alert tone="danger">{errorMessage(error)}</Alert>
        ) : data.length === 0 ? (
          <EmptyState icon={Eye} title="No one has opened your files yet">When a hiring team reads your application, you'll see it here.</EmptyState>
        ) : (
          <ul className="divide-y divide-border">
            {data.map((e) => (
              <li key={e.id} className="flex flex-col gap-1 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="text-sm font-medium">{e.company_name || "A hiring team"}</p>
                  <p className="truncate text-sm text-muted">
                    {e.viewer_name ? `${e.viewer_name} opened ` : "Opened "}
                    {e.label}
                  </p>
                </div>
                <time dateTime={e.accessed_at} className="shrink-0 text-xs text-muted">{when(e.accessed_at)}</time>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
