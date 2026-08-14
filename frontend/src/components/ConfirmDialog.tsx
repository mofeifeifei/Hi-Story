export async function confirmAction(message: string): Promise<boolean> {
  return window.confirm(message);
}
