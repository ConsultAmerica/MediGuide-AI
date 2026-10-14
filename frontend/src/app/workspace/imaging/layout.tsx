"use client";

import { Suspense, useEffect, type ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ImagingWorkspace } from "./ImagingWorkspace";
import { imagingUrl, parseImagingRoute } from "./imaging-route";
import { useWorkspaceContext } from "../_state/WorkspaceStateProvider";
import { API_URL } from "../_state/workspace-shared";

// Imaging is hosted here, in the layout, rather than in its pages: a layout
// stays mounted across /workspace/imaging and /workspace/imaging/<id>, so
// moving between the browser and a study (or back) keeps in-flight work
// such as a sample report that is still uploading. The pages render
// nothing; the URL alone decides which screen ImagingWorkspace shows.
function ImagingHost() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { pushToast } = useWorkspaceContext();
  const route = parseImagingRoute(pathname, new URLSearchParams(searchParams.toString()));

  // The older ?openStudy=<id> link is rewritten to the study's own URL.
  const legacyStudyLink = searchParams.get("openStudy");
  useEffect(() => {
    if (legacyStudyLink && route.kind === "detail") router.replace(imagingUrl(route));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [legacyStudyLink]);

  return <ImagingWorkspace apiUrl={API_URL} pushToast={pushToast} route={route} />;
}

export default function ImagingLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <Suspense fallback={null}>
        <ImagingHost />
      </Suspense>
      {children}
    </>
  );
}
