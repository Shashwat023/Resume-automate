/**
 * Triggers a browser download of a JSON string via a data: URI and a
 * programmatically-clicked anchor. Extracted from pages/SettingsPage.tsx's
 * handleExportData as part of the clean-architecture restructure — same
 * data: URI construction, same download attribute, same click() trigger.
 */
export function downloadJson(dataStr: string, filename: string): void {
  const dataUri = 'data:application/json;charset=utf-8,' + encodeURIComponent(dataStr);
  const linkElement = document.createElement('a');
  linkElement.setAttribute('href', dataUri);
  linkElement.setAttribute('download', filename);
  linkElement.click();
}
