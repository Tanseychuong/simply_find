import { Hammer } from "lucide-react";
import { Container, EmptyState } from "../components/ui";

/* Stands in for screens that are still being built. */
export default function Placeholder({ title }) {
  return (
    <Container className="py-8 sm:py-12">
      <EmptyState icon={Hammer} title={title}>
        This page is on its way.
      </EmptyState>
    </Container>
  );
}
