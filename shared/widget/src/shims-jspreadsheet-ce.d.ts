/**
 * Ambient types for jspreadsheet-ce.
 * SchemaView async-imports SchemaSheet; modules that exclude SchemaSheet
 * still typecheck that graph and may not resolve the package from shared/widget.
 * Sale/fleet/freight that ship the real package can override via tsconfig paths.
 */
declare module 'jspreadsheet-ce' {
  type Worksheet = Record<string, unknown> & {
    setComments?: (cell: string, tip: string) => void
    getData?: (highlighted?: boolean, processed?: boolean) => unknown[][]
  }

  type Helpers = {
    getCellNameFromCoords: (col: number, row: number) => string
  }

  type JspreadsheetFn = {
    (el: HTMLElement, options: Record<string, unknown>): Worksheet[]
    destroy: (el: HTMLElement) => void
    helpers: Helpers
  }

  const jspreadsheet: JspreadsheetFn
  export default jspreadsheet
}
