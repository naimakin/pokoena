import { ComparisonTabs } from "./tabs";

export default function Page({ searchParams }: { searchParams: { tab?: string } }) {
  return <ComparisonTabs initial={searchParams.tab} />;
}
