import { lazy, Suspense } from "react";
import { AppShell } from "./components/AppShell";
import { useAppStore } from "./stores/appStore";

const ExportPage = lazy(() => import("./pages/ExportPage").then((module) => ({ default: module.ExportPage })));
const LibraryPage = lazy(() => import("./pages/PagedLibraryPage").then((module) => ({ default: module.LibraryPage })));
const OutlinePage = lazy(() => import("./pages/OutlinePage").then((module) => ({ default: module.OutlinePage })));
const ProjectPage = lazy(() => import("./pages/ProjectPage").then((module) => ({ default: module.ProjectPage })));
const RecordsPage = lazy(() => import("./pages/PagedRecordsPage").then((module) => ({ default: module.RecordsPage })));
const SettingsPage = lazy(() => import("./pages/FullSettingsPage").then((module) => ({ default: module.SettingsPage })));
const WritingPage = lazy(() => import("./pages/WritingPage").then((module) => ({ default: module.WritingPage })));

export default function App() {
  const page = useAppStore((state) => state.page);
  return <AppShell><Suspense fallback={<div className="loading-block">正在载入页面...</div>}>{page === "project" ? <ProjectPage /> : page === "outline" ? <OutlinePage /> : page === "writing" ? <WritingPage /> : page === "library" ? <LibraryPage /> : page === "export" ? <ExportPage /> : page === "records" ? <RecordsPage /> : <SettingsPage />}</Suspense></AppShell>;
}
