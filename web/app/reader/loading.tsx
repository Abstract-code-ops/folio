import { LoadingScreen } from "@/components/ui/loading-screen";

export default function Loading() {
  return (
    <LoadingScreen
      messages={[
        "Loading book…",
        "Fetching sections…",
        "Loading chat…",
        "Preparing notes…",
        "Almost there…",
      ]}
    />
  );
}
