import { Bookmark } from "lucide-react";
import { opportunitiesApi } from "../api/opportunities";
import { errorMessage } from "../api/client";
import OpportunityCard, { CardSkeleton } from "../components/opportunities/OpportunityCard";
import { Alert, ButtonLink, Container, EmptyState } from "../components/ui";
import { useApi, useTitle } from "../lib/hooks";

export default function Saved() {
  useTitle("Saved roles");
  const { data, loading, error } = useApi((signal) => opportunitiesApi.saved({ page_size: 100 }, { signal }), []);
  // Paginated ({results}) or a plain list, depending on the endpoint's settings.
  const items = Array.isArray(data) ? data : data?.results || [];

  return (
    <Container className="py-8">
      <h1 className="mb-6 text-3xl font-bold tracking-tight">Saved roles</h1>
      {error ? (
        <Alert tone="danger">{errorMessage(error)}</Alert>
      ) : loading && !data ? (
        <div className="grid grid-cols-1 gap-3">{Array.from({ length: 3 }, (_, i) => <CardSkeleton key={i} />)}</div>
      ) : items.length === 0 ? (
        <EmptyState icon={Bookmark} title="Nothing saved yet" action={<ButtonLink to="/opportunities">Find roles</ButtonLink>}>
          Tap the bookmark on any role to keep it here for later.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-3">
          {items.map((s) => <OpportunityCard key={s.id} opp={s.opportunity} />)}
        </div>
      )}
    </Container>
  );
}
