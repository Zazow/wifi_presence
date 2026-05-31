// Minimal ambient types for qrcode-generator (the package ships JS only).
declare module "qrcode-generator" {
  interface QRCode {
    addData(data: string): void;
    make(): void;
    createDataURL(cellSize?: number, margin?: number): string;
    createSvgTag(cellSize?: number, margin?: number): string;
  }
  type ErrorCorrectionLevel = "L" | "M" | "Q" | "H";
  function qrcode(typeNumber: number, errorCorrectionLevel: ErrorCorrectionLevel): QRCode;
  export default qrcode;
}
