import { SearchX } from "lucide-react";
import { ButtonLink, Container, EmptyState } from "../components/ui";

export default function NotFound() {
  return (
    <Container className="py-12">
      <EmptyState
        icon={SearchX}
        title="We couldn't find that page"
        action={<ButtonLink to="/opportunities">Browse roles</ButtonLink>}
      >
        The link may be old, or the listing may have closed.
      </EmptyState>
    </Container>
  );
}
