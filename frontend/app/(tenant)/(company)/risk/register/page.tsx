import { RegisterTabs } from "./tabs";

export default function Page({ searchParams }: { searchParams: { view?: string } }) {
  return <RegisterTabs initial={searchParams.view} />;
}
