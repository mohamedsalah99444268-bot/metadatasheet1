import PdfViewer from "./PdfViewer";
import { useApp } from "../state/AppContext";
import { pdfUrl } from "../api";
import { EmptyState, ErrorState, Icon, LoadingState } from "./ui";

export default function DocumentViewer({ height = "100%" }: { height?: number | string }) {
  const {
    selectedDocumentId,
    selectedDocument,
    pages,
    highlight,
    targetPage,
    focusToken,
    detailLoading,
    detailError,
  } = useApp();

  if (selectedDocumentId == null) {
    return <EmptyState icon="file" title="Aucune fiche ouverte" description="Ouvrez un document depuis l’explorateur de composants ou importez un nouveau PDF pour inspecter ses pages source." />;
  }
  if (detailLoading && pages.length === 0) return <LoadingState label="Préparation de la visionneuse PDF…" />;
  if (detailError) return <ErrorState message={detailError} />;

  return (
    <div className="document-viewer" style={{ height }}>
      <PdfViewer
        documentId={selectedDocumentId}
        pages={pages}
        highlight={highlight}
        targetPage={targetPage}
        focusToken={focusToken}
        title={selectedDocument?.original_filename}
      />
      <a className="btn btn-ghost pdf-open-link" href={pdfUrl(selectedDocumentId)} target="_blank" rel="noreferrer">
        <Icon name="arrow" size={15} />
        Ouvrir le PDF d’origine
      </a>
    </div>
  );
}
