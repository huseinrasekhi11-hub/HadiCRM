import useMediaQuery from "../hooks/useMediaQuery";
import Dashboard from "./Dashboard";
import Today from "./Today";

// One product, two postures:
// phone -> execution home ("what do I do now?")
// desktop -> management dashboard (rebuilt in Part 9)
// 800px matches the AppShell mobile breakpoint.
export default function Home() {
  const isMobile = useMediaQuery("(max-width: 800px)");
  return isMobile ? <Today /> : <Dashboard />;
}
