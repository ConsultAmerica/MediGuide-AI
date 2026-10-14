import type { Modality } from "./imaging-types";
import { DETAIL_TABS, type DetailTab } from "./ImagingStudyDetail";

/**
 * Imaging's sub-views live in the URL so refresh, shared links and
 * Back/Forward all land on the same screen:
 *
 *   /workspace/imaging                         modality browser
 *   /workspace/imaging?modality=mri            studies for one modality
 *   /workspace/imaging?view=history            imaging history
 *   /workspace/imaging?view=compare&with=<id>  compare (optionally preset)
 *   /workspace/imaging/<id>?tab=report&page=2  one study
 *
 * `?openStudy=<id>` is the older study link and is still understood.
 */
export type ImagingRoute =
  | { kind: "landing" }
  | { kind: "list"; modality: Modality }
  | { kind: "history" }
  | { kind: "compare"; withStudyId: string | null }
  | { kind: "detail"; studyId: string; tab: DetailTab | null; page: number | null };

const BASE = "/workspace/imaging";
const MODALITIES: readonly Modality[] = ["xray", "ct", "mri", "ultrasound", "pet_ct"];

export function parseImagingRoute(pathname: string, params: URLSearchParams): ImagingRoute {
  const rest = pathname.startsWith(`${BASE}/`) ? pathname.slice(BASE.length + 1) : "";
  const studyId = decodeURIComponent(rest.split("/")[0] || "") || params.get("openStudy");
  if (studyId) {
    const tab = params.get("tab") as DetailTab | null;
    const page = Number(params.get("page"));
    return {
      kind: "detail",
      studyId,
      tab: tab && DETAIL_TABS.includes(tab) ? tab : null,
      page: Number.isInteger(page) && page > 0 ? page : null,
    };
  }
  const view = params.get("view");
  if (view === "history") return { kind: "history" };
  if (view === "compare") return { kind: "compare", withStudyId: params.get("with") };
  const modality = params.get("modality") as Modality | null;
  if (modality && MODALITIES.includes(modality)) return { kind: "list", modality };
  return { kind: "landing" };
}

export function imagingUrl(route: ImagingRoute): string {
  switch (route.kind) {
    case "landing":
      return BASE;
    case "list":
      return `${BASE}?modality=${encodeURIComponent(route.modality)}`;
    case "history":
      return `${BASE}?view=history`;
    case "compare":
      return route.withStudyId ? `${BASE}?view=compare&with=${encodeURIComponent(route.withStudyId)}` : `${BASE}?view=compare`;
    case "detail": {
      const params = new URLSearchParams();
      if (route.tab) params.set("tab", route.tab);
      if (route.page) params.set("page", String(route.page));
      const query = params.toString();
      return `${BASE}/${encodeURIComponent(route.studyId)}${query ? `?${query}` : ""}`;
    }
  }
}
