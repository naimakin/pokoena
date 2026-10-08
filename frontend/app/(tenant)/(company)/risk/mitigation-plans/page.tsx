import { MitigationTabs } from "./tabs";

export default function Page({ searchParams }: { searchParams: { tab?: string } }) {
  return <MitigationTabs initial={searchParams.tab} />;
}
